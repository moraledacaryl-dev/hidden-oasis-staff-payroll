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


APP_VERSION = "0.1.1-api-wrapper-schema-tolerant"
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


def table_columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def table_exists(conn: Any, table: str) -> bool:
    row = fetchone(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return bool(row and int(row.get("c") or 0) > 0)


def normalize_employee(row: dict[str, Any], department_name: str | None = None) -> dict[str, Any]:
    """Return the stable web/API employee shape even for older SQLite schemas.

    The live server database may not have newer columns such as department_id.
    This function keeps the API contract stable without altering the database.
    """
    return clean_row(
        {
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
        }
    )


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
            employee_columns = sorted(table_columns(conn, "employees"))
        return {
            "app": "hidden-oasis-staff-payroll",
            "api_version": APP_VERSION,
            "database_path": str(db_path),
            "database_exists": db_path.exists(),
            "table_count": table_count,
            "employee_count": employees,
            "payroll_run_count": payroll_runs,
            "employee_columns": employee_columns,
            "mode": "api-wrapper-first-migration",
        }

    @app.get(f"{API_PREFIX}/staff/employees", dependencies=[Depends(require_api_key)])
    def list_employees(
        status_filter: str | None = Query(default=None, description="Optional employee status filter."),
        department_id: int | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        with db_conn(read_only=True) as conn:
            columns = table_columns(conn, "employees")
            departments = department_lookup(conn)
            sql = "SELECT * FROM employees WHERE 1=1"
            params: list[Any] = []
            if status_filter and "status" in columns:
                sql += " AND status=?"
                params.append(status_filter)
            if department_id is not None and "department_id" in columns:
                sql += " AND department_id=?"
                params.append(department_id)
            order_col = "full_name" if "full_name" in columns else "id"
            sql += f" ORDER BY {order_col}"
            rows = fetchall(conn, sql, params)
            results = []
            for row in rows:
                dept_name = None
                if row.get("department_id") is not None:
                    dept_name = departments.get(int(row["department_id"]))
                results.append(normalize_employee(row, dept_name))
            return results

    @app.get(f"{API_PREFIX}/staff/employees/{{employee_id}}", dependencies=[Depends(require_api_key)])
    def get_employee(employee_id: int) -> dict[str, Any]:
        with db_conn(read_only=True) as conn:
            row = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,))
            departments = department_lookup(conn)
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found.")
        dept_name = None
        if row.get("department_id") is not None:
            dept_name = departments.get(int(row["department_id"]))
        return normalize_employee(row, dept_name)

    @app.get(f"{API_PREFIX}/schedules", dependencies=[Depends(require_api_key)])
    def list_schedules(
        start_date: date,
        end_date: date,
        department_id: int | None = Query(default=None),
        employee_id: int | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            employee_columns = table_columns(conn, "employees")
            sql = """
                SELECT s.*, e.employee_code, e.full_name
                FROM schedules s
                JOIN employees e ON e.id=s.employee_id
                WHERE s.work_date BETWEEN ? AND ?
            """
            params: list[Any] = [period_start, period_end]
            if department_id is not None and "department_id" in employee_columns:
                sql += " AND e.department_id=?"
                params.append(department_id)
            if employee_id is not None:
                sql += " AND s.employee_id=?"
                params.append(employee_id)
            sql += " ORDER BY s.work_date, e.full_name, s.shift_start"
            rows = clean_rows(fetchall(conn, sql, params))
            for row in rows:
                row.setdefault("department_id", None)
                row.setdefault("department_name", None)
            return rows

    @app.get(f"{API_PREFIX}/time-logs", dependencies=[Depends(require_api_key)])
    def list_time_logs(
        start_date: date,
        end_date: date,
        employee_id: int | None = Query(default=None),
        attendance_status: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        period_start, period_end = parse_date_order(start_date, end_date)
        with db_conn(read_only=True) as conn:
            sql = """
                SELECT tl.*, e.employee_code, e.full_name
                FROM time_logs tl
                JOIN employees e ON e.id=tl.employee_id
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
            rows = clean_rows(fetchall(conn, sql, params))
            for row in rows:
                row.setdefault("department_id", None)
                row.setdefault("department_name", None)
            return rows

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
