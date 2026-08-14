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

from api.security import (
    IMPERSONATION_TTL_SECONDS,
    ROLE_OWNER,
    ROLE_PAYROLL,
    ROLE_STAFF,
    ROLE_SUPERVISOR,
    SESSION_TTL_SECONDS,
    configured_db_path,
    current_user_from_token,
    db_conn,
    public_user,
    require_api_key,
    require_roles,
    role_to_key,
    session_users_from_payload,
    sign_payload,
    verify_token,
)

from core.auth import authenticate_user, verify_totp
from core.mfa_security import (
    consume_recovery_code,
    decrypt_mfa_secret,
)
from core.audit import log_audit
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.login_security import clear_login_failures, lock_remaining_seconds, record_login_failure
from core.payroll_engine import compute_payroll
from core.quality import (
    build_payroll_preflight_checks,
    canonical_attendance_review_items,
    summarize_checks,
)

APP_VERSION = "1.0.0"
API_PREFIX = "/api/v1"

class PayrollPreviewRequest(BaseModel):
    period_start: date = Field(..., description="Cutoff start date, YYYY-MM-DD")
    period_end: date = Field(..., description="Cutoff end date, YYYY-MM-DD")

class LoginRequest(BaseModel):
    display_name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    otp: str | None = Field(default=None, min_length=6, max_length=6)
    recovery_code: str | None = Field(default=None, min_length=8, max_length=64)

class AttendanceDecisionRequest(BaseModel):
    decision: str = Field(..., description="Approved, Rejected, or Needs Correction")
    reason: str | None = Field(default=None)
    approved_ot_hours: float = Field(default=0, ge=0)

class ApiMessage(BaseModel):
    ok: bool
    message: str

def env_csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]



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
                # Temporary passwords are now a dismissible UI reminder, not an API blocker.
                # Staff can continue using self-service pages and change the password when convenient.
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
            if int(user.get("mfa_enabled") or 0):
                if payload.otp and payload.recovery_code:
                    raise HTTPException(
                        status_code=400,
                        detail="Provide either an authenticator code or a recovery code, not both.",
                    )

                recovery_used = False

                if payload.otp:
                    second_factor_ok = verify_totp(
                        decrypt_mfa_secret(user.get("mfa_secret")),
                        payload.otp,
                    )
                elif payload.recovery_code:
                    try:
                        stored_codes = json.loads(
                            user.get("mfa_recovery_codes") or "[]"
                        )
                    except (TypeError, json.JSONDecodeError):
                        stored_codes = []

                    if not isinstance(stored_codes, list):
                        stored_codes = []

                    second_factor_ok, remaining_codes = (
                        consume_recovery_code(
                            [str(item) for item in stored_codes],
                            payload.recovery_code,
                        )
                    )

                    if second_factor_ok:
                        conn.execute(
                            """
                            UPDATE app_users
                            SET mfa_recovery_codes=?
                            WHERE id=?
                            """,
                            (
                                json.dumps(remaining_codes),
                                user["id"],
                            ),
                        )
                        recovery_used = True
                else:
                    raise HTTPException(
                        status_code=428,
                        detail="Authenticator code or recovery code required.",
                    )

                if not second_factor_ok:
                    record_login_failure(
                        conn,
                        payload.display_name,
                        ip_address,
                    )
                    log_audit(
                        conn,
                        actor=payload.display_name.strip() or None,
                        action="MFA verification failed",
                        table_name="app_users",
                        record_id=user.get("id"),
                        details={"ip_address": ip_address},
                    )
                    conn.commit()
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authenticator or recovery code is invalid.",
                    )

                if recovery_used:
                    log_audit(
                        conn,
                        actor=user.get("display_name"),
                        action="MFA recovery code used",
                        table_name="app_users",
                        record_id=user.get("id"),
                        details={"ip_address": ip_address},
                    )

            clear_login_failures(conn, payload.display_name, ip_address)

            logged_in_at = now_iso()
            conn.execute(
                "UPDATE app_users SET last_login_at=? WHERE id=?",
                (logged_in_at, user["id"]),
            )
            user["last_login_at"] = logged_in_at

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

    @app.get(
        f"{API_PREFIX}/attendance/exceptions",
        dependencies=[Depends(require_api_key)],
    )
    def attendance_exceptions(
        start_date: date,
        end_date: date,
        user: dict[str, Any] = Depends(
            require_roles(ROLE_OWNER, ROLE_SUPERVISOR)
        ),
    ) -> list[dict[str, Any]]:
        start, end = parse_date_order(start_date, end_date)

        with db_conn(read_only=True) as conn:
            rows = canonical_attendance_review_items(
                conn,
                start,
                end,
            )

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
