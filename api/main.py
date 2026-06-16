from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.payroll_engine import compute_payroll
from core.quality import build_payroll_preflight_checks, summarize_checks


APP_VERSION = "0.1.0-api-wrapper"
API_PREFIX = "/api/v1"


class PayrollPreviewRequest(BaseModel):
    period_start: date = Field(..., description="Cutoff start date, YYYY-MM-DD")
    period_end: date = Field(..., description="Cutoff end date, YYYY-MM-DD")


class ApiMessage(BaseModel):
    ok: bool
    message: str


def env_csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def configured_db_path() -> Path:
    return Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DB_PATH))).expanduser()


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Require an API key only when STAFF_PAYROLL_API_KEY is configured.

    This keeps local migration testing simple while allowing the production deployment
    to enforce a shared API key before the full auth layer is added.
    """
    expected = os.getenv("STAFF_PAYROLL_API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


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


def payroll_result_to_api(result: Any) -> dict[str, Any]:
    data = asdict(result) if is_dataclass(result) else dict(result)
    data["warnings"] = data.get("warnings") or []
    return clean_row(data)


def parse_date_order(start_date: date, end_date: date) -> tuple[str, str]:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date cannot be before start date.")
    return start_date.isoformat(), end_date.isoformat()


def build_app() -> FastAPI:
    app = FastAPI(
        title="Hidden Oasis Staff Payroll API",
        version=APP_VERSION,
        description=(
            "Production migration API wrapper around the existing Staff Payroll "
            "SQLite database and Python payroll engine. Payroll formulas remain in core/payroll_engine.py."
        ),
    )

    origins = env_csv("STAFF_PAYROLL_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=ApiMessage)
    def health() -> ApiMessage:
        return ApiMessage(ok=True, message="Staff Payroll API is running.")

    @app.get(f"{API_PREFIX}/meta", dependencies=[Depends(require_api_key)])
    def meta() -> dict[str, Any]:
        db_path = configured_db_path()
        with db_conn(read_only=True) as conn:
            table_count = fetchone(
                conn,
                "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
            )["c"]
            employees = fetchone(conn, "SELECT COUNT(*) AS c FROM employees")["c"]
            payroll_runs = fetchone(conn, "SELECT COUNT(*) AS c FROM payroll_runs")["c"]
        return {
            "app": "hidden-oasis-staff-payroll",
            "api_version": APP_VERSION,
            "database_path": str(db_path),
            "database_exists": db_path.exists(),
            "table_count": table_count,
            "employee_count": employees,
            "payroll_run_count": payroll_runs,
            "mode": "api-wrapper-first-migration",
        }

    @app.get(f"{API_PREFIX}/staff/employees", dependencies=[Depends(require_api_key)])
    def list_employees(
        status_filter: str | None = Query(default=None, description="Optional employee status filter."),
        department_id: int | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT e.id, e.employee_code, e.full_name, e.department_id, d.name AS department_name,
                   e.position, e.employment_type, e.status, e.default_shift_start,
                   e.default_shift_end, e.standard_paid_hours, e.break_mins,
                   e.benefits_sss, e.benefits_philhealth, e.benefits_pagibig, e.benefits_tax,
                   e.created_at
            FROM employees e
            LEFT JOIN departments d ON d.id=e.department_id
            WHERE 1=1
        """
        params: list[Any] = []
        if status_filter:
            sql += " AND e.status=?"
            params.append(status_filter)
        if department_id is not None:
            sql += " AND e.department_id=?"
            params.append(department_id)
        sql += " ORDER BY e.full_name"
        with db_conn(read_only=True) as conn:
            return clean_rows(fetchall(conn, sql, params))

    @app.get(f"{API_PREFIX}/staff/employees/{{employee_id}}", dependencies=[Depends(require_api_key)])
    def get_employee(employee_id: int) -> dict[str, Any]:
        with db_conn(read_only=True) as conn:
            row = fetchone(
                conn,
                """
                SELECT e.id, e.employee_code, e.full_name, e.department_id, d.name AS department_name,
                       e.position, e.employment_type, e.status, e.default_shift_start,
                       e.default_shift_end, e.standard_paid_hours, e.break_mins,
                       e.benefits_sss, e.benefits_philhealth, e.benefits_pagibig, e.benefits_tax,
                       e.created_at
                FROM employees e
                LEFT JOIN departments d ON d.id=e.department_id
                WHERE e.id=?
                """,
                (employee_id,),
            )
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found.")
        return clean_row(row)

    @app.get(f"{API_PREFIX}/schedules", dependencies=[Depends(require_api_key)])
    def list_schedules(
        start_date: date,
        end_date: date,
        department_id: int | None = Query(default=None),
        employee_id: int | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        sql = """
            SELECT s.*, e.employee_code, e.full_name, e.department_id, d.name AS department_name
            FROM schedules s
            JOIN employees e ON e.id=s.employee_id
            LEFT JOIN departments d ON d.id=e.department_id
            WHERE s.work_date BETWEEN ? AND ?
        """
        params: list[Any] = [period_start, period_end]
        if department_id is not None:
            sql += " AND e.department_id=?"
            params.append(department_id)
        if employee_id is not None:
            sql += " AND s.employee_id=?"
            params.append(employee_id)
        sql += " ORDER BY s.work_date, e.full_name, s.shift_start"
        with db_conn(read_only=True) as conn:
            return clean_rows(fetchall(conn, sql, params))

    @app.get(f"{API_PREFIX}/time-logs", dependencies=[Depends(require_api_key)])
    def list_time_logs(
        start_date: date,
        end_date: date,
        employee_id: int | None = Query(default=None),
        attendance_status: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        sql = """
            SELECT tl.*, e.employee_code, e.full_name, d.name AS department_name
            FROM time_logs tl
            JOIN employees e ON e.id=tl.employee_id
            LEFT JOIN departments d ON d.id=e.department_id
            WHERE tl.work_date BETWEEN ? AND ?
        """
        params: list[Any] = [period_start, period_end]
        if employee_id is not None:
            sql += " AND tl.employee_id=?"
            params.append(employee_id)
        if attendance_status:
            sql += " AND tl.attendance_status=?"
            params.append(attendance_status)
        sql += " ORDER BY tl.work_date, e.full_name, tl.actual_in"
        with db_conn(read_only=True) as conn:
            return clean_rows(fetchall(conn, sql, params))

    @app.get(f"{API_PREFIX}/payroll/preflight", dependencies=[Depends(require_api_key)])
    def payroll_preflight(period_start: date, period_end: date) -> dict[str, Any]:
        start, end = parse_date_order(period_start, period_end)
        with db_conn(read_only=True) as conn:
            checks = build_payroll_preflight_checks(conn, start, end)
        return {
            "period_start": start,
            "period_end": end,
            "summary": summarize_checks(checks),
            "checks": checks,
        }

    @app.post(f"{API_PREFIX}/payroll/preview", dependencies=[Depends(require_api_key)])
    def payroll_preview(payload: PayrollPreviewRequest) -> dict[str, Any]:
        start, end = parse_date_order(payload.period_start, payload.period_end)
        with db_conn(read_only=True) as conn:
            checks = build_payroll_preflight_checks(conn, start, end)
            results = [payroll_result_to_api(item) for item in compute_payroll(conn, start, end)]
        totals = {
            "employees": len(results),
            "gross_pay": round(sum(float(row.get("gross_pay") or 0) for row in results), 2),
            "net_pay": round(sum(float(row.get("net_pay") or 0) for row in results), 2),
            "total_deductions": round(sum(float(row.get("total_deductions") or 0) for row in results), 2),
            "cash_advance_deduction": round(sum(float(row.get("cash_advance_deduction") or 0) for row in results), 2),
        }
        return {
            "period_start": start,
            "period_end": end,
            "summary": summarize_checks(checks),
            "checks": checks,
            "totals": totals,
            "items": results,
            "mode": "preview_only_no_save",
        }

    return app


app = build_app()
