from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.main import configured_db_path, table_columns
from api.security import require_api_key, require_roles
from core.audit import log_audit
from core.db import fetchone, get_conn
from core.integration_outbox import enqueue_employee_sync

router = APIRouter(prefix="/api/v1/staff", dependencies=[Depends(require_api_key)])


class EmployeeEditorPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    employee_code: str = Field(..., min_length=1)
    full_name: str = Field(..., min_length=1)
    department_name: str | None = None
    position: str | None = None
    employment_type: str | None = None
    status: str = "Active"
    default_shift_start: str | None = Field(
        default=None,
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    default_shift_end: str | None = Field(
        default=None,
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    standard_shift_hours: float | None = Field(default=None, ge=0, le=24)
    unpaid_break_minutes: int | None = Field(default=None, ge=0, le=1440)
    benefits_sss: int | None = Field(default=None, ge=0, le=1)
    benefits_philhealth: int | None = Field(default=None, ge=0, le=1)
    benefits_pagibig: int | None = Field(default=None, ge=0, le=1)
    benefits_tax: int | None = Field(default=None, ge=0, le=1)


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


def _duplicate_employee(
    conn: Any,
    code: str,
    name: str,
    exclude_id: int | None = None,
) -> dict[str, Any] | None:
    if exclude_id is None:
        return fetchone(
            conn,
            """
            SELECT id FROM employees
            WHERE lower(employee_code)=lower(?) OR lower(full_name)=lower(?)
            LIMIT 1
            """,
            (code, name),
        )
    return fetchone(
        conn,
        """
        SELECT id FROM employees
        WHERE id<>?
          AND (lower(employee_code)=lower(?) OR lower(full_name)=lower(?))
        LIMIT 1
        """,
        (exclude_id, code, name),
    )


PAYROLL_FIELDS = {
    "benefits_sss",
    "benefits_philhealth",
    "benefits_pagibig",
    "benefits_tax",
}


def _employee_values(
    conn: Any,
    payload: EmployeeEditorPayload,
    *,
    include_payroll_fields: bool,
) -> dict[str, Any]:
    columns = table_columns(conn, "employees")
    department_name = _clean(payload.department_name)
    candidates: dict[str, Any] = {
        "employee_code": payload.employee_code.strip(),
        "full_name": _clean(payload.full_name),
        "position": _clean(payload.position) or "",
        "employment_type": _clean(payload.employment_type) or "Hourly",
        "status": _clean(payload.status) or "Active",
        "default_shift_start": _clean(payload.default_shift_start),
        "default_shift_end": _clean(payload.default_shift_end),
    }
    if payload.standard_shift_hours is not None:
        candidates["standard_shift_hours"] = payload.standard_shift_hours
    if payload.unpaid_break_minutes is not None:
        candidates["unpaid_break_minutes"] = payload.unpaid_break_minutes
    if include_payroll_fields:
        candidates.update(
            {
                field: int(bool(getattr(payload, field)))
                for field in PAYROLL_FIELDS
                if getattr(payload, field) is not None
            }
        )
    if "department_id" in columns:
        candidates["department_id"] = _department_id(conn, department_name)
    elif "department" in columns:
        candidates["department"] = department_name or "General"
    if "updated_at" in columns:
        candidates["updated_at"] = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    return {key: value for key, value in candidates.items() if key in columns}


def _queue_employee_sync(conn: Any, employee_id: int, actor: str | None) -> None:
    event_ids = enqueue_employee_sync(conn, employee_id)
    log_audit(
        conn,
        actor=actor,
        action="Employee integration events queued",
        table_name="employees",
        record_id=employee_id,
        details={"integration_event_ids": event_ids},
    )


@router.post("/employees")
def add_employee(
    payload: EmployeeEditorPayload,
    user: dict[str, Any] = Depends(require_roles("owner", "payroll", "supervisor")),
) -> dict[str, Any]:
    code = payload.employee_code.strip()
    name = _clean(payload.full_name) or ""
    conn = get_conn(configured_db_path())
    try:
        duplicate = _duplicate_employee(conn, code, name)
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"Employee code or name already exists on employee #{duplicate['id']}.",
            )
        can_manage_payroll = user.get("role_key") in {"owner", "payroll"}
        if not can_manage_payroll and PAYROLL_FIELDS.intersection(payload.model_fields_set):
            raise HTTPException(
                status_code=403,
                detail="General Managers cannot change payroll benefit settings.",
            )
        values = _employee_values(
            conn,
            payload,
            include_payroll_fields=can_manage_payroll,
        )
        if not can_manage_payroll:
            columns = table_columns(conn, "employees")
            values.update({field: 0 for field in PAYROLL_FIELDS if field in columns})
        if "created_at" in table_columns(conn, "employees"):
            values["created_at"] = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        cursor = conn.execute(
            f"INSERT INTO employees({','.join(values)}) VALUES({','.join('?' for _ in values)})",
            tuple(values.values()),
        )
        employee_id = int(cursor.lastrowid)
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="Employee created",
            table_name="employees",
            record_id=employee_id,
            details={"employee_code": code, "role": user.get("role_key")},
        )
        _queue_employee_sync(conn, employee_id, user.get("display_name"))
        conn.commit()
        return {"ok": True, "employee_id": employee_id, "message": f"{name} added."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/employees/{employee_id}")
def edit_employee(
    employee_id: int,
    payload: EmployeeEditorPayload,
    user: dict[str, Any] = Depends(require_roles("owner", "payroll", "supervisor")),
) -> dict[str, Any]:
    code = payload.employee_code.strip()
    name = _clean(payload.full_name) or ""
    conn = get_conn(configured_db_path())
    try:
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        duplicate = _duplicate_employee(conn, code, name, employee_id)
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"Another employee already uses this code or name (employee #{duplicate['id']}).",
            )
        can_manage_payroll = user.get("role_key") in {"owner", "payroll"}
        if not can_manage_payroll and PAYROLL_FIELDS.intersection(payload.model_fields_set):
            raise HTTPException(
                status_code=403,
                detail="General Managers cannot change payroll benefit settings.",
            )
        values = _employee_values(
            conn,
            payload,
            include_payroll_fields=can_manage_payroll,
        )
        conn.execute(
            f"UPDATE employees SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
            (*values.values(), employee_id),
        )
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="Employee updated",
            table_name="employees",
            record_id=employee_id,
            details={"employee_code": code, "role": user.get("role_key")},
        )
        _queue_employee_sync(conn, employee_id, user.get("display_name"))
        conn.commit()
        return {"ok": True, "employee_id": employee_id, "message": f"{name} updated."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()