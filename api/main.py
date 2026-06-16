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

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.auth import authenticate_user
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.payroll_engine import compute_payroll
from core.quality import build_payroll_preflight_checks, summarize_checks


APP_VERSION = "0.1.3-api-wrapper-role-guards"
API_PREFIX = "/api/v1"
SESSION_TTL_SECONDS = 12 * 60 * 60
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


class ApiMessage(BaseModel):
    ok: bool
    message: str


def env_csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def configured_db_path() -> Path:
    return Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DB_PATH))).expanduser()


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = os.getenv("STAFF_PAYROLL_API_KEY")
    if not expected:
        return
    if x_api_key != expected:
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


def iso_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


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
    if text in {"owner", "admin", "administrator"}:
        return ROLE_OWNER
    if text in {"payroll", "payroll_admin", "hr", "hr_payroll"}:
        return ROLE_PAYROLL
    if text in {"supervisor", "manager", "department_head"}:
        return ROLE_SUPERVISOR
    if text in {"staff", "employee"}:
        return ROLE_STAFF
    return ROLE_STAFF


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return clean_row({
        "id": user.get("id"),
        "display_name": user.get("display_name") or "",
        "role": user.get("role") or "Staff",
        "role_key": role_to_key(user.get("role")),
        "active": int(user.get("active") or 0),
        "must_change_password": int(user.get("must_change_password") or 0),
        "last_login_at": user.get("last_login_at"),
    })


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
        if not hmac.compare_digest(b64url_decode(signature), expected):
            raise ValueError("bad signature")
        payload = json.loads(b64url_decode(body).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")


def current_user_from_token(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    payload = verify_token(authorization.removeprefix("Bearer ").strip())
    with db_conn(read_only=True) as conn:
        user = fetchone(conn, "SELECT * FROM app_users WHERE id=? AND active=1", (payload.get("sub"),))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists or is inactive.")
    return public_user(user)


def require_authenticated_user(user: dict[str, Any] = Depends(current_user_from_token)) -> dict[str, Any]:
    return user


def require_roles(*allowed_roles: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    normalized_allowed = {role_to_key(role) for role in allowed_roles}

    def _require_role(user: dict[str, Any] = Depends(require_authenticated_user)) -> dict[str, Any]:
        if user.get("role_key") not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(sorted(normalized_allowed))}.",
            )
        return user

    return _require_role


def normalize_employee(row: dict[str, Any], department_name: str | None = None) -> dict[str, Any]:
    return clean_row({
        "id": row.get("id"),
        "employee_code": row.get("employee_code") or row.get("code") or "",
        "full_name": row.get("full_name") or row.get("name") or "",
        "department_id": row.get("department_id"),
        "department_name": department_name or row.get("department_name") or row.get("department") or None,
        "position": row.get("position") or row.get("role") or None,
        "employment_type": row.get("employment_type") or None,
        "status": row.get("status") or "Active",
        "default_shift_start": row.get("default_shift_start"),
        "default_shift_end": row.get("default_shift_end"),
        "standard_paid_hours": row.get("standard_paid_hours"),
        "break_mins": row.get("break_mins"),
        "benefits_sss": int(row.get("benefits_sss") or 0),
        "benefits_philhealth": int(row.get("benefits_philhealth") or 0),
        "benefits_pagibig": int(row.get("benefits_pagibig") or 0),
        "benefits_tax": int(row.get("benefits_tax") or 0),
        "created_at": row.get("created_at") or "",
    })


def department_lookup(conn: Any) -> dict[int, str]:
    if not table_exists(conn, "departments"):
        return {}
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


def build_app() -> FastAPI:
    app = FastAPI(title="Hidden Oasis Staff Payroll API", version=APP_VERSION, description="Migration API wrapper around the existing SQLite database and Python payroll engine.")
    origins = env_csv("STAFF_PAYROLL_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

    @app.get("/health", response_model=ApiMessage)
    def health() -> ApiMessage:
        return ApiMessage(ok=True, message="Staff Payroll API is running.")

    @app.post(f"{API_PREFIX}/auth/login", dependencies=[Depends(require_api_key)])
    def auth_login(payload: LoginRequest) -> dict[str, Any]:
        with db_conn(read_only=False) as conn:
            user = authenticate_user(conn, payload.display_name.strip(), payload.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
        safe_user = public_user(user)
        now = int(time.time())
        token = sign_payload({"sub": safe_user["id"], "role": safe_user["role_key"], "iat": now, "exp": now + SESSION_TTL_SECONDS})
        return {"access_token": token, "token_type": "bearer", "expires_in": SESSION_TTL_SECONDS, "user": safe_user}

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

    @app.get(f"{API_PREFIX}/meta", dependencies=[Depends(require_api_key)])
    def meta() -> dict[str, Any]:
        db_path = configured_db_path()
        with db_conn(read_only=True) as conn:
            table_count = fetchone(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")["c"]
            employees = fetchone(conn, "SELECT COUNT(*) AS c FROM employees")["c"]
            payroll_runs = fetchone(conn, "SELECT COUNT(*) AS c FROM payroll_runs")["c"]
            employee_columns = sorted(table_columns(conn, "employees"))
        return {"app": "hidden-oasis-staff-payroll", "api_version": APP_VERSION, "database_path": str(db_path), "database_exists": db_path.exists(), "table_count": table_count, "employee_count": employees, "payroll_run_count": payroll_runs, "employee_columns": employee_columns, "mode": "api-wrapper-first-migration"}

    @app.get(f"{API_PREFIX}/staff/employees", dependencies=[Depends(require_api_key)])
    def list_employees(status_filter: str | None = Query(default=None), department_id: int | None = Query(default=None)) -> list[dict[str, Any]]:
        with db_conn(read_only=True) as conn:
            columns = table_columns(conn, "employees")
            departments = department_lookup(conn)
            sql = "SELECT * FROM employees WHERE 1=1"
            params: list[Any] = []
            if status_filter and "status" in columns:
                sql += " AND status=?"; params.append(status_filter)
            if department_id is not None and "department_id" in columns:
                sql += " AND department_id=?"; params.append(department_id)
            sql += f" ORDER BY {'full_name' if 'full_name' in columns else 'id'}"
            rows = fetchall(conn, sql, params)
            return [normalize_employee(row, departments.get(int(row["department_id"])) if row.get("department_id") is not None else None) for row in rows]

    @app.get(f"{API_PREFIX}/staff/employees/{{employee_id}}", dependencies=[Depends(require_api_key)])
    def get_employee(employee_id: int) -> dict[str, Any]:
        with db_conn(read_only=True) as conn:
            row = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,))
            departments = department_lookup(conn)
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found.")
        return normalize_employee(row, departments.get(int(row["department_id"])) if row.get("department_id") is not None else None)

    @app.get(f"{API_PREFIX}/schedules", dependencies=[Depends(require_api_key)])
    def list_schedules(start_date: date, end_date: date, department_id: int | None = Query(default=None), employee_id: int | None = Query(default=None)) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            employee_columns = table_columns(conn, "employees")
            sql = """SELECT s.*, e.employee_code, e.full_name FROM schedules s JOIN employees e ON e.id=s.employee_id WHERE s.work_date BETWEEN ? AND ?"""
            params: list[Any] = [period_start, period_end]
            if department_id is not None and "department_id" in employee_columns:
                sql += " AND e.department_id=?"; params.append(department_id)
            if employee_id is not None:
                sql += " AND s.employee_id=?"; params.append(employee_id)
            sql += " ORDER BY s.work_date, e.full_name, s.shift_start"
            rows = clean_rows(fetchall(conn, sql, params))
            for row in rows:
                row.setdefault("department_id", None); row.setdefault("department_name", None)
            return rows

    @app.get(f"{API_PREFIX}/time-logs", dependencies=[Depends(require_api_key)])
    def list_time_logs(start_date: date, end_date: date, employee_id: int | None = Query(default=None), attendance_status: str | None = Query(default=None)) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            sql = """SELECT tl.*, e.employee_code, e.full_name FROM time_logs tl JOIN employees e ON e.id=tl.employee_id WHERE tl.work_date BETWEEN ? AND ?"""
            params: list[Any] = [period_start, period_end]
            if employee_id is not None:
                sql += " AND tl.employee_id=?"; params.append(employee_id)
            if attendance_status:
                sql += " AND tl.attendance_status=?"; params.append(attendance_status)
            sql += " ORDER BY tl.work_date, e.full_name, tl.actual_in"
            rows = clean_rows(fetchall(conn, sql, params))
            for row in rows:
                row.setdefault("department_id", None); row.setdefault("department_name", None)
            return rows

    @app.get(f"{API_PREFIX}/payroll/preflight", dependencies=[Depends(require_api_key)])
    def payroll_preflight(period_start: date, period_end: date) -> dict[str, Any]:
        start, end = parse_date_order(period_start, period_end)
        with db_conn(read_only=True) as conn:
            checks = build_payroll_preflight_checks(conn, start, end)
        return {"period_start": start, "period_end": end, "summary": summarize_checks(checks), "checks": checks}

    @app.post(f"{API_PREFIX}/payroll/preview", dependencies=[Depends(require_api_key)])
    def payroll_preview(payload: PayrollPreviewRequest) -> dict[str, Any]:
        start, end = parse_date_order(payload.period_start, payload.period_end)
        with db_conn(read_only=True) as conn:
            checks = build_payroll_preflight_checks(conn, start, end)
            results = [payroll_result_to_api(item) for item in compute_payroll(conn, start, end)]
        totals = {"employees": len(results), "gross_pay": round(sum(float(row.get("gross_pay") or 0) for row in results), 2), "net_pay": round(sum(float(row.get("net_pay") or 0) for row in results), 2), "total_deductions": round(sum(float(row.get("total_deductions") or 0) for row in results), 2), "cash_advance_deduction": round(sum(float(row.get("cash_advance_deduction") or 0) for row in results), 2)}
        return {"period_start": start, "period_end": end, "summary": summarize_checks(checks), "checks": checks, "totals": totals, "items": results, "mode": "preview_only_no_save"}

    return app


app = build_app()
