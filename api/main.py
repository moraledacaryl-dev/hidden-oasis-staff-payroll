from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from core.auth import authenticate_user
from core.audit import log_audit
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.login_security import clear_login_failures, lock_remaining_seconds, record_login_failure
from core.payroll_engine import compute_payroll
from core.quality import build_payroll_preflight_checks, summarize_checks

APP_VERSION = "1.0.0"
API_PREFIX = "/api/v1"
SESSION_TTL_SECONDS = 12 * 60 * 60
IMPERSONATION_TTL_SECONDS = 30 * 60
ROLE_OWNER = "owner"
ROLE_PAYROLL = "payroll"
ROLE_SUPERVISOR = "supervisor"
ROLE_STAFF = "staff"

class PayrollPreviewRequest(BaseModel):
    period_start: date = Field(..., description="Cutoff start date, YYYY-MM-DD")
    period_end: date = Field(..., description="Cutoff end date, YYYY-MM-DD")

class LoginRequest(BaseModel):
    display_name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

class AttendanceDecisionRequest(BaseModel):
    decision: str = Field(..., description="Approved, Rejected, or Needs Correction")
    reason: str | None = Field(default=None)
    approved_ot_hours: float = Field(default=0, ge=0)

class ApiMessage(BaseModel):
    ok: bool
    message: str

def env_csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]

def configured_db_path() -> Path:
    return Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DB_PATH))).expanduser()

def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = os.getenv("STAFF_PAYROLL_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")

@contextmanager
def db_conn(read_only: bool = False) -> Iterator[Any]:
    db_path = configured_db_path()
    if read_only:
        if not db_path.exists():
            raise HTTPException(status_code=500, detail=f"Database not found: {db_path}")
        uri = f"file:{db_path.resolve()}?mode=ro"
        import sqlite3
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn = get_conn(db_path)
    try:
        yield conn
    finally:
        conn.close()

def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")

def iso_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value

def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: iso_value(value) for key, value in row.items()}

def clean_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [clean_row(row) for row in rows]

def table_columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def table_exists(conn: Any, table: str) -> bool:
    row = fetchone(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return bool(row and int(row.get("c") or 0) > 0)

def role_to_key(role: str | None) -> str:
    text = (role or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"owner", "admin", "administrator"}: return ROLE_OWNER
    if text in {"payroll", "payroll_admin", "hr", "hr_payroll"}: return ROLE_PAYROLL
    if text in {"supervisor", "manager", "general_manager", "department_head"}: return ROLE_SUPERVISOR
    if text in {"staff", "employee"}: return ROLE_STAFF
    return ROLE_STAFF

def public_user(user: dict[str, Any]) -> dict[str, Any]:
    role_key = role_to_key(user.get("role"))
    return clean_row(
        {
            "id": user.get("id"),
            "display_name": user.get("display_name") or "",
            "role": "General Manager" if role_key == ROLE_SUPERVISOR else user.get("role") or "Staff",
            "role_key": role_key,
            "active": int(user.get("active") or 0),
            "must_change_password": int(user.get("must_change_password") or 0),
            "mfa_enabled": 0,
            "mfa_setup_required": 0,
            "employee_id": user.get("employee_id"),
            "session_version": int(user.get("session_version") or 1),
            "last_login_at": user.get("last_login_at"),
        }
    )

def token_secret() -> str:
    return os.getenv("STAFF_PAYROLL_SESSION_SECRET") or os.getenv("STAFF_PAYROLL_API_KEY") or "dev-only-change-staff-payroll-session-secret"

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

def sign_payload(payload: dict[str, Any]) -> str:
    body = b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(token_secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return f"{body}.{b64url_encode(sig)}"

def verify_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(token_secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url_decode(signature), expected): raise ValueError("bad signature")
        payload = json.loads(b64url_decode(body).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()): raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")

def session_users_from_payload(conn: Any, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    user = fetchone(conn, "SELECT * FROM app_users WHERE id=? AND active=1", (payload.get("sub"),))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists or is inactive.")
    if int(payload.get("sv") or 1) != int(user.get("session_version") or 1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked.")

    impersonator_id = payload.get("imp_by")
    if impersonator_id is None:
        return user, None
    impersonator = fetchone(conn, "SELECT * FROM app_users WHERE id=? AND active=1", (impersonator_id,))
    if (
        not impersonator
        or int(impersonator.get("id") or 0) == int(user.get("id") or 0)
        or role_to_key(impersonator.get("role")) != ROLE_OWNER
        or int(payload.get("imp_sv") or 0) != int(impersonator.get("session_version") or 1)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Owner view session is no longer valid.")
    return user, impersonator

def log_impersonated_action(
    context: dict[str, Any],
    *,
    method: str,
    path: str,
    status_code: int,
    ip_address: str | None,
) -> None:
    with db_conn(read_only=False) as conn:
        log_audit(
            conn,
            actor=context["owner_name"],
            action="Owner acted as user",
            table_name="app_users",
            record_id=context["target_id"],
            details={
                "owner_id": context["owner_id"],
                "target": context["target_name"],
                "method": method,
                "path": path,
                "status_code": status_code,
                "ip_address": ip_address,
            },
        )
        conn.commit()

def current_user_from_token(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    payload = verify_token(authorization.removeprefix("Bearer ").strip())
    with db_conn(read_only=True) as conn:
        user, impersonator = session_users_from_payload(conn, payload)
    result = public_user(user)
    if impersonator:
        result.update(
            {
                "is_impersonating": 1,
                "impersonator_id": int(impersonator["id"]),
                "impersonator_name": impersonator.get("display_name") or "Owner",
                "must_change_password": 0,
                "mfa_setup_required": 0,
            }
        )
    return result

def require_authenticated_user(user: dict[str, Any] = Depends(current_user_from_token)) -> dict[str, Any]:
    return user

def require_roles(*allowed_roles: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    allowed = {role_to_key(role) for role in allowed_roles}
    def _require_role(user: dict[str, Any] = Depends(require_authenticated_user)) -> dict[str, Any]:
        if user.get("role_key") not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action requires one of these roles: {', '.join(sorted(allowed))}.")
        return user
    return _require_role

def normalize_employee(row: dict[str, Any], department_name: str | None = None, include_private: bool = True) -> dict[str, Any]:
    return clean_row({"id": row.get("id"), "employee_code": row.get("employee_code") or row.get("code") or "", "full_name": row.get("full_name") or row.get("name") or "", "department_id": row.get("department_id"), "department_name": department_name or row.get("department_name") or row.get("department") or None, "position": row.get("position") or row.get("role") or None, "employment_type": row.get("employment_type") or None, "status": row.get("status") or "Active", "default_shift_start": row.get("default_shift_start"), "default_shift_end": row.get("default_shift_end"), "standard_shift_hours": row.get("standard_shift_hours"), "unpaid_break_minutes": row.get("unpaid_break_minutes"), "benefits_sss": int(row.get("benefits_sss") or 0) if include_private else 0, "benefits_philhealth": int(row.get("benefits_philhealth") or 0) if include_private else 0, "benefits_pagibig": int(row.get("benefits_pagibig") or 0) if include_private else 0, "benefits_tax": int(row.get("benefits_tax") or 0) if include_private else 0, "created_at": row.get("created_at") or ""})

def department_lookup(conn: Any) -> dict[int, str]:
    if not table_exists(conn, "departments"): return {}
    rows = fetchall(conn, "SELECT id, name FROM departments")
    return {int(row["id"]): str(row["name"]) for row in rows if row.get("id") is not None}

def payroll_result_to_api(result: Any) -> dict[str, Any]:
    data = asdict(result) if is_dataclass(result) else dict(result)
    data["warnings"] = data.get("warnings") or []
    return clean_row(data)

def parse_date_order(start_date: date, end_date: date) -> tuple[str, str]:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date cannot be before start date.")
    return start_date.isoformat(), end_date.isoformat()

def attendance_exception_sql() -> str:
    return """
        SELECT tl.*, e.employee_code, e.full_name, e.department, e.position
        FROM time_logs tl
        JOIN employees e ON e.id=tl.employee_id
        WHERE tl.work_date BETWEEN ? AND ?
          AND (
            COALESCE(tl.is_absent, 0) = 1
            OR tl.actual_in IS NULL
            OR tl.actual_out IS NULL
            OR COALESCE(tl.ot_status, 'None') = 'Pending'
            OR COALESCE(tl.attendance_status, '') IN ('Needs Review', 'Needs Correction', 'Rejected')
          )
    """

def build_app() -> FastAPI:
    app = FastAPI(
        title="Hidden Oasis Staff Payroll API",
        version=APP_VERSION,
        description="Staff operations and payroll API.",
    )
    origins = env_csv(
        "STAFF_PAYROLL_CORS_ORIGINS",
        "http://localhost:3001,http://127.0.0.1:3001",
    )
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

    @app.middleware("http")
    async def enforce_account_security(request: Request, call_next):
        path = request.url.path
        impersonation_context: dict[str, Any] | None = None
        exempt = {
            f"{API_PREFIX}/auth/login",
            f"{API_PREFIX}/auth/me",
            f"{API_PREFIX}/auth/change-password",
        }
        authorization = request.headers.get("Authorization", "")
        if request.method != "OPTIONS" and path.startswith(API_PREFIX) and authorization.startswith("Bearer "):
            try:
                payload = verify_token(authorization.removeprefix("Bearer ").strip())
                with db_conn(read_only=True) as conn:
                    user, impersonator = session_users_from_payload(conn, payload)
                if impersonator:
                    impersonation_context = {
                        "owner_id": int(impersonator["id"]),
                        "owner_name": impersonator.get("display_name") or "Owner",
                        "target_id": int(user["id"]),
                        "target_name": user.get("display_name") or "",
                    }
                if path not in exempt and int(user.get("must_change_password") or 0):
                    return JSONResponse(
                        {"detail": "Change your temporary password first.", "code": "password_change_required"},
                        status_code=428,
                    )
            except HTTPException:
                pass
        response = await call_next(request)
        if impersonation_context and request.method not in {"GET", "HEAD", "OPTIONS"}:
            log_impersonated_action(
                impersonation_context,
                method=request.method,
                path=path,
                status_code=response.status_code,
                ip_address=request.client.host if request.client else None,
            )
        return response

    @app.get("/health", response_model=ApiMessage)
    def health() -> ApiMessage:
        return ApiMessage(ok=True, message="Staff Payroll API is running.")

    @app.post(f"{API_PREFIX}/auth/login", dependencies=[Depends(require_api_key)])
    def auth_login(payload: LoginRequest, request: Request) -> dict[str, Any]:
        ip_address = request.client.host if request.client else "unknown"
        with db_conn(read_only=False) as conn:
            remaining = lock_remaining_seconds(conn, payload.display_name, ip_address)
            if remaining:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed attempts. Try again in {remaining} seconds.",
                )
            user = authenticate_user(
                conn,
                payload.display_name.strip(),
                payload.password,
                record_login=False,
            )
            if not user:
                record_login_failure(conn, payload.display_name, ip_address)
                log_audit(
                    conn,
                    actor=payload.display_name.strip() or None,
                    action="Login failed",
                    table_name="app_users",
                    details={"ip_address": ip_address},
                )
                conn.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
            clear_login_failures(conn, payload.display_name, ip_address)
            public = public_user(user)
            token = sign_payload(
                {
                    "sub": user["id"],
                    "role": public["role_key"],
                    "sv": int(user.get("session_version") or 1),
                    "exp": int(time.time()) + SESSION_TTL_SECONDS,
                }
            )
            log_audit(
                conn,
                actor=public["display_name"],
                action="Login success",
                table_name="app_users",
                record_id=user["id"],
                details={"ip_address": ip_address},
            )
            conn.commit()
        return {"access_token": token, "token_type": "bearer", "user": public, "expires_in": SESSION_TTL_SECONDS}

    @app.get(f"{API_PREFIX}/auth/me", dependencies=[Depends(require_api_key)])
    def auth_me(user: dict[str, Any] = Depends(current_user_from_token)) -> dict[str, Any]:
        return {"user": user}

    @app.get(f"{API_PREFIX}/auth/can-approve-payroll", dependencies=[Depends(require_api_key)])
    def auth_can_approve_payroll(user: dict[str, Any] = Depends(require_roles(ROLE_OWNER))) -> dict[str, Any]:
        return {"ok": True, "action": "approve_payroll", "user": user}

    @app.get(f"{API_PREFIX}/auth/can-manage-attendance", dependencies=[Depends(require_api_key)])
    def auth_can_manage_attendance(user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_SUPERVISOR))) -> dict[str, Any]:
        return {"ok": True, "action": "manage_attendance", "user": user}

    @app.get(f"{API_PREFIX}/auth/can-preview-payroll", dependencies=[Depends(require_api_key)])
    def auth_can_preview_payroll(user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL))) -> dict[str, Any]:
        return {"ok": True, "action": "preview_payroll", "user": user}

    @app.get(f"{API_PREFIX}/attendance/exceptions", dependencies=[Depends(require_api_key)])
    def attendance_exceptions(start_date: date, end_date: date, user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_SUPERVISOR))) -> list[dict[str, Any]]:
        start, end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            rows = fetchall(conn, attendance_exception_sql() + " ORDER BY tl.work_date, e.full_name", (start, end))
        return clean_rows(rows)

    @app.post(f"{API_PREFIX}/attendance/time-logs/{{time_log_id}}/decision", dependencies=[Depends(require_api_key)])
    def attendance_decision(time_log_id: int, payload: AttendanceDecisionRequest, user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_SUPERVISOR))) -> dict[str, Any]:
        decision = payload.decision.strip().title()
        if decision not in {"Approved", "Rejected", "Needs Correction"}:
            raise HTTPException(status_code=422, detail="Decision must be Approved, Rejected, or Needs Correction.")
        attendance_status = "Approved" if decision == "Approved" else "Needs Review"
        ot_status = "Approved" if payload.approved_ot_hours > 0 and decision == "Approved" else ("Rejected" if decision == "Rejected" else "None")
        timestamp = now_iso()
        with db_conn(read_only=False) as conn:
            row = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (time_log_id,))
            if not row: raise HTTPException(status_code=404, detail="Time log not found.")
            conn.execute("""
                UPDATE time_logs
                SET attendance_status=?, reviewed_by=?, reviewed_at=?, approved_ot_hours=?, ot_status=?, notes=COALESCE(notes, '') || ?
                WHERE id=?
            """, (attendance_status, user["display_name"], timestamp, float(payload.approved_ot_hours or 0), ot_status, f"\n[{timestamp}] {decision}: {payload.reason or ''}", time_log_id))
            conn.execute("""
                INSERT INTO attendance_reviews (time_log_id, reviewer, decision, reason, approved_ot_hours, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (time_log_id, user["display_name"], decision, payload.reason or "", float(payload.approved_ot_hours or 0), timestamp))
            log_audit(
                conn,
                actor=user.get("display_name"),
                action=f"Attendance {decision.lower()}",
                table_name="time_logs",
                record_id=time_log_id,
                details={
                    "approved_ot_hours": float(payload.approved_ot_hours or 0),
                    "reason": payload.reason or "",
                },
            )
            conn.commit()
            updated = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (time_log_id,))
        return {"ok": True, "time_log": clean_row(updated or {}), "decision": decision, "reviewed_by": user["display_name"], "reviewed_at": timestamp}

    @app.get(f"{API_PREFIX}/attendance/reviews", dependencies=[Depends(require_api_key)])
    def attendance_reviews(start_date: date, end_date: date, user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_SUPERVISOR))) -> list[dict[str, Any]]:
        start, end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            rows = fetchall(conn, """
                SELECT ar.*, tl.work_date, e.employee_code, e.full_name, e.department, e.position
                FROM attendance_reviews ar
                JOIN time_logs tl ON tl.id=ar.time_log_id
                JOIN employees e ON e.id=tl.employee_id
                WHERE tl.work_date BETWEEN ? AND ?
                ORDER BY ar.created_at DESC, ar.id DESC
                LIMIT 100
            """, (start, end))
        return clean_rows(rows)

    @app.get(f"{API_PREFIX}/meta", dependencies=[Depends(require_api_key)])
    def meta(
        user: dict[str, Any] = Depends(
            require_roles(ROLE_OWNER, ROLE_PAYROLL, ROLE_SUPERVISOR)
        ),
    ) -> dict[str, Any]:
        db_path = configured_db_path()
        with db_conn(read_only=True) as conn:
            table_count = fetchone(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")["c"]
            employees = fetchone(conn, "SELECT COUNT(*) AS c FROM employees")["c"]
            payroll_runs = fetchone(conn, "SELECT COUNT(*) AS c FROM payroll_runs")["c"]
            employee_columns = sorted(table_columns(conn, "employees"))
        return {"app": "hidden-oasis-staff-payroll", "api_version": APP_VERSION, "database_path": str(db_path), "database_exists": db_path.exists(), "table_count": table_count, "employee_count": employees, "payroll_run_count": payroll_runs, "employee_columns": employee_columns, "mode": "production"}

    @app.get(f"{API_PREFIX}/staff/employees", dependencies=[Depends(require_api_key)])
    def list_employees(status_filter: str | None = Query(default=None), department_id: int | None = Query(default=None), user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL, ROLE_SUPERVISOR))) -> list[dict[str, Any]]:
        with db_conn(read_only=True) as conn:
            columns = table_columns(conn, "employees"); departments = department_lookup(conn)
            sql = "SELECT * FROM employees WHERE 1=1"; params: list[Any] = []
            if status_filter and "status" in columns: sql += " AND status=?"; params.append(status_filter)
            if department_id is not None and "department_id" in columns: sql += " AND e.department_id=?"; params.append(department_id)
            sql += f" ORDER BY {'full_name' if 'full_name' in columns else 'id'}"
            rows = fetchall(conn, sql, params)
            include_private = user.get("role_key") in {ROLE_OWNER, ROLE_PAYROLL}
            return [normalize_employee(row, departments.get(int(row["department_id"])) if row.get("department_id") is not None else None, include_private=include_private) for row in rows]

    @app.get(f"{API_PREFIX}/staff/employees/{{employee_id}}", dependencies=[Depends(require_api_key)])
    def get_employee(employee_id: int, user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL, ROLE_SUPERVISOR))) -> dict[str, Any]:
        with db_conn(read_only=True) as conn:
            row = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,)); departments = department_lookup(conn)
        if not row: raise HTTPException(status_code=404, detail="Employee not found.")
        include_private = user.get("role_key") in {ROLE_OWNER, ROLE_PAYROLL}
        return normalize_employee(row, departments.get(int(row["department_id"])) if row.get("department_id") is not None else None, include_private=include_private)

    @app.get(f"{API_PREFIX}/schedules", dependencies=[Depends(require_api_key)])
    def list_schedules(
        start_date: date,
        end_date: date,
        department_id: int | None = Query(default=None),
        employee_id: int | None = Query(default=None),
        user: dict[str, Any] = Depends(
            require_roles(ROLE_OWNER, ROLE_PAYROLL, ROLE_SUPERVISOR)
        ),
    ) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            employee_columns = table_columns(conn, "employees")
            sql = """SELECT s.*, e.employee_code, e.full_name FROM schedules s JOIN employees e ON e.id=s.employee_id WHERE s.work_date BETWEEN ? AND ?"""; params: list[Any] = [period_start, period_end]
            if department_id is not None and "department_id" in employee_columns: sql += " AND e.department_id=?"; params.append(department_id)
            if employee_id is not None: sql += " AND s.employee_id=?"; params.append(employee_id)
            sql += " ORDER BY s.work_date, e.full_name, s.shift_start"
            rows = clean_rows(fetchall(conn, sql, params))
            for row in rows: row.setdefault("department_id", None); row.setdefault("department_name", None)
            return rows

    @app.get(f"{API_PREFIX}/time-logs", dependencies=[Depends(require_api_key)])
    def list_time_logs(
        start_date: date,
        end_date: date,
        employee_id: int | None = Query(default=None),
        attendance_status: str | None = Query(default=None),
        user: dict[str, Any] = Depends(
            require_roles(ROLE_OWNER, ROLE_PAYROLL, ROLE_SUPERVISOR)
        ),
    ) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            sql = """SELECT tl.*, e.employee_code, e.full_name FROM time_logs tl JOIN employees e ON e.id=tl.employee_id WHERE tl.work_date BETWEEN ? AND ?"""; params: list[Any] = [period_start, period_end]
            if employee_id is not None: sql += " AND tl.employee_id=?"; params.append(employee_id)
            if attendance_status: sql += " AND tl.attendance_status=?"; params.append(attendance_status)
            sql += " ORDER BY tl.work_date, e.full_name, tl.actual_in"
            rows = clean_rows(fetchall(conn, sql, params))
            for row in rows: row.setdefault("department_id", None); row.setdefault("department_name", None)
            return rows

    @app.get(f"{API_PREFIX}/payroll/preflight", dependencies=[Depends(require_api_key)])
    def payroll_preflight(period_start: date, period_end: date, user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL))) -> dict[str, Any]:
        start, end = parse_date_order(period_start, period_end)
        with db_conn(read_only=True) as conn: checks = build_payroll_preflight_checks(conn, start, end)
        return {"period_start": start, "period_end": end, "summary": summarize_checks(checks), "checks": checks}

    @app.post(f"{API_PREFIX}/payroll/preview", dependencies=[Depends(require_api_key)])
    def payroll_preview(payload: PayrollPreviewRequest, user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL))) -> dict[str, Any]:
        start, end = parse_date_order(payload.period_start, payload.period_end)
        with db_conn(read_only=True) as conn:
            checks = build_payroll_preflight_checks(conn, start, end)
            results = [payroll_result_to_api(item) for item in compute_payroll(conn, start, end)]
        totals = {"employees": len(results), "gross_pay": round(sum(float(row.get("gross_pay") or 0) for row in results), 2), "net_pay": round(sum(float(row.get("net_pay") or 0) for row in results), 2), "total_deductions": round(sum(float(row.get("total_deductions") or 0) for row in results), 2), "cash_advance_deduction": round(sum(float(row.get("cash_advance_deduction") or 0) for row in results), 2)}
        return {"period_start": start, "period_end": end, "summary": summarize_checks(checks), "checks": checks, "totals": totals, "items": results, "mode": "preview_only_no_save"}

    return app

app = build_app()
