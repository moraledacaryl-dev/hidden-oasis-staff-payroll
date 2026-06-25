from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

from api.main import app, current_user_from_token, require_api_key, table_columns
from api.payroll_drafts_v2 import router as payroll_drafts_router
from api.payroll_return import router as payroll_return_router
from api.payroll_review import router as payroll_review_router
from api.my_payroll import router as my_payroll_router
from api.payroll_mark_paid import router as payroll_mark_paid_router
from api.payroll_corrections import router as payroll_corrections_router
from api.payroll_audit_events import router as payroll_audit_events_router
from api.payroll_revision_controls import router as revision_controls_router
from api.payroll_revision_workflow_v3 import router as revision_workflow_router
from api.production_health import router as production_health_router
from api.hr_records import router as hr_records_router
from api.payslip_distribution import router as payslip_distribution_router
from api.schedules import router as schedules_router
from api.schedule_actuals import router as schedule_actuals_router
from api.schedule_rest_days import router as schedule_rest_days_router
from api.schedule_leave_statuses import router as schedule_leave_statuses_router
from api.sil_leave import router as sil_leave_router
from api.schedule_migration import router as schedule_migration_router
from api.schedule_publication import router as schedule_publication_router
from api.users import router as users_router
from api.staff_self_service import router as staff_self_service_router
from api.staff_published_portal import router as staff_published_portal_router
from core.runtime_guard import validate_runtime_environment
from api.attendance_compliance import router as attendance_compliance_router
from api.cash_advances_v4 import router as cash_advances_router
from api.cash_repayments_v2 import router as cash_repayments_router
from api.cash_advance_corrections_v2 import router as cash_advance_corrections_router
from api.performance_reviews import router as performance_reviews_router
from api.payroll_adjustments_v3 import router as payroll_adjustments_router
from api.payroll_recalculate import router as payroll_recalculate_router
from core.db import DB_PATH, fetchone, get_conn


class CreateAppUserPayload(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=120)
    role: str = Field(default="Staff", min_length=2, max_length=40)
    employee_id: int | None = None


class EmployeeEditorPayload(BaseModel):
    employee_code: str = Field(..., min_length=1)
    full_name: str = Field(..., min_length=1)
    department_name: str | None = None
    position: str | None = None
    employment_type: str | None = None
    status: str = "Active"
    default_shift_start: str | None = None
    default_shift_end: str | None = None
    standard_paid_hours: float | None = None
    break_mins: int | None = None
    benefits_sss: int = 0
    benefits_philhealth: int = 0
    benefits_pagibig: int = 0
    benefits_tax: int = 0


def _owner_user(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Owner access required.")
    return user


def _employee_editor_user(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Only owner or payroll can add or edit employees.")
    return user


def _clean(value: str | None) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text or None


def _department_id(conn: Any, name: str | None) -> int | None:
    clean = _clean(name)
    if not clean or "department_id" not in table_columns(conn, "employees"):
        return None
    row = fetchone(conn, "SELECT id FROM departments WHERE lower(name)=lower(?)", (clean,))
    if row:
        return int(row["id"])
    return int(conn.execute("INSERT INTO departments(name) VALUES(?)", (clean,)).lastrowid)


def _duplicate_employee(conn: Any, code: str, name: str, exclude_id: int | None = None) -> dict[str, Any] | None:
    if exclude_id is None:
        return fetchone(conn, "SELECT id FROM employees WHERE lower(employee_code)=lower(?) OR lower(full_name)=lower(?) LIMIT 1", (code, name))
    return fetchone(conn, "SELECT id FROM employees WHERE id<>? AND (lower(employee_code)=lower(?) OR lower(full_name)=lower(?)) LIMIT 1", (exclude_id, code, name))


def _employee_values(conn: Any, payload: EmployeeEditorPayload) -> dict[str, Any]:
    columns = table_columns(conn, "employees")
    department_name = _clean(payload.department_name)
    candidates: dict[str, Any] = {
        "employee_code": payload.employee_code.strip(),
        "full_name": _clean(payload.full_name),
        "position": _clean(payload.position),
        "employment_type": _clean(payload.employment_type),
        "status": _clean(payload.status) or "Active",
        "default_shift_start": _clean(payload.default_shift_start),
        "default_shift_end": _clean(payload.default_shift_end),
        "standard_paid_hours": payload.standard_paid_hours,
        "break_mins": payload.break_mins,
        "benefits_sss": int(bool(payload.benefits_sss)),
        "benefits_philhealth": int(bool(payload.benefits_philhealth)),
        "benefits_pagibig": int(bool(payload.benefits_pagibig)),
        "benefits_tax": int(bool(payload.benefits_tax)),
    }
    if "department_id" in columns:
        candidates["department_id"] = _department_id(conn, department_name)
    elif "department" in columns:
        candidates["department"] = department_name
    if "updated_at" in columns:
        candidates["updated_at"] = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    return {key: value for key, value in candidates.items() if key in columns}


@app.on_event("startup")
def validate_runtime() -> None:
    validate_runtime_environment()


@app.post("/api/v1/users")
def create_app_user(
    payload: CreateAppUserPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _owner_user(authorization, x_api_key)
    display_name = _clean(payload.display_name) or ""
    roles = {"owner": "Owner", "payroll": "Payroll", "supervisor": "Supervisor", "staff": "Staff"}
    role = roles.get(str(payload.role or "").strip().lower())
    if not role:
        raise HTTPException(status_code=422, detail="Role must be Owner, Payroll, Supervisor, or Staff.")
    conn = get_conn(DB_PATH)
    try:
        user_columns = table_columns(conn, "app_users")
        if "employee_id" not in user_columns:
            conn.execute("ALTER TABLE app_users ADD COLUMN employee_id INTEGER")
            conn.commit()
        if fetchone(conn, "SELECT id FROM app_users WHERE lower(display_name)=lower(?)", (display_name,)):
            raise HTTPException(status_code=409, detail="A user with that login name already exists.")
        if payload.employee_id is not None:
            if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
                raise HTTPException(status_code=404, detail="Employee not found.")
            if fetchone(conn, "SELECT id FROM app_users WHERE employee_id=?", (payload.employee_id,)):
                raise HTTPException(status_code=409, detail="That employee is already linked to another user.")
        created_at = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        cursor = conn.execute(
            """
            INSERT INTO app_users(display_name, role, password_hash, active, must_change_password, created_at, employee_id)
            VALUES (?, ?, NULL, 0, 1, ?, ?)
            """,
            (display_name, role, created_at, payload.employee_id),
        )
        conn.commit()
        return {"ok": True, "user_id": int(cursor.lastrowid), "message": "User created."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.post("/api/v1/staff/employees")
def add_employee(payload: EmployeeEditorPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    _employee_editor_user(authorization, x_api_key)
    code = payload.employee_code.strip()
    name = _clean(payload.full_name) or ""
    conn = get_conn(DB_PATH)
    try:
        duplicate = _duplicate_employee(conn, code, name)
        if duplicate:
            raise HTTPException(status_code=409, detail=f"Employee code or name already exists on employee #{duplicate['id']}.")
        values = _employee_values(conn, payload)
        if "created_at" in table_columns(conn, "employees"):
            values["created_at"] = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        cursor = conn.execute(
            f"INSERT INTO employees({','.join(values)}) VALUES({','.join('?' for _ in values)})",
            tuple(values.values()),
        )
        conn.commit()
        return {"ok": True, "employee_id": int(cursor.lastrowid), "message": f"{name} added."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.post("/api/v1/staff/employees/{employee_id}")
def edit_employee(employee_id: int, payload: EmployeeEditorPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    _employee_editor_user(authorization, x_api_key)
    code = payload.employee_code.strip()
    name = _clean(payload.full_name) or ""
    conn = get_conn(DB_PATH)
    try:
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        duplicate = _duplicate_employee(conn, code, name, employee_id)
        if duplicate:
            raise HTTPException(status_code=409, detail=f"Another employee already uses this code or name (employee #{duplicate['id']}).")
        values = _employee_values(conn, payload)
        conn.execute(
            f"UPDATE employees SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
            (*values.values(), employee_id),
        )
        conn.commit()
        return {"ok": True, "employee_id": employee_id, "message": f"{name} updated."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


app.include_router(payroll_drafts_router)
app.include_router(payroll_return_router)
app.include_router(payroll_review_router)
app.include_router(my_payroll_router)
app.include_router(payroll_mark_paid_router)
app.include_router(payroll_corrections_router)
app.include_router(payroll_audit_events_router)
app.include_router(schedule_migration_router)
app.include_router(revision_controls_router)
app.include_router(revision_workflow_router)
app.include_router(production_health_router)
app.include_router(hr_records_router)
app.include_router(payslip_distribution_router)
app.include_router(schedules_router)
app.include_router(schedule_actuals_router)
app.include_router(schedule_rest_days_router)
app.include_router(schedule_leave_statuses_router)
app.include_router(sil_leave_router)
app.include_router(users_router)
app.include_router(schedule_publication_router)
app.include_router(staff_self_service_router)
app.include_router(staff_published_portal_router)
app.include_router(attendance_compliance_router)
app.include_router(cash_advances_router)
app.include_router(cash_repayments_router)
app.include_router(cash_advance_corrections_router)
app.include_router(performance_reviews_router)
app.include_router(payroll_adjustments_router)
app.include_router(payroll_recalculate_router)
