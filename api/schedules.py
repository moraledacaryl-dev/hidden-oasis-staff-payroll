from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

POSITIONS = {"Receptionist", "Cook", "Barista", "Bartender", "Security", "Housekeeper", "Other"}

class ShiftPayload(BaseModel):
    employee_id: int | None = None
    shift_date: date
    start_time: str
    end_time: str
    position: str = "Other"
    department: str | None = None
    break_minutes: int = 60
    notes: str | None = None

class DuplicateShiftPayload(BaseModel):
    shift_date: date | None = None

class CopyWeekPayload(BaseModel):
    from_week_start: date
    to_week_start: date


def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            position TEXT NOT NULL DEFAULT 'Other',
            department TEXT,
            break_minutes INTEGER NOT NULL DEFAULT 60,
            status TEXT NOT NULL DEFAULT 'Draft',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_shifts_date ON scheduled_shifts(shift_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_shifts_employee ON scheduled_shifts(employee_id)")
    conn.commit()


def hours_for_shift(shift_date: str, start_time: str, end_time: str, break_minutes: int) -> float:
    start = datetime.fromisoformat(f"{shift_date}T{start_time}")
    end = datetime.fromisoformat(f"{shift_date}T{end_time}")
    if end <= start:
        end += timedelta(days=1)
    gross = (end - start).total_seconds() / 3600
    return max(0.0, gross - max(0, break_minutes) / 60)


def clean_shift(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["planned_paid_hours"] = hours_for_shift(str(row.get("shift_date")), str(row.get("start_time")), str(row.get("end_time")), int(row.get("break_minutes") or 0))
    data["is_overnight"] = str(row.get("end_time")) <= str(row.get("start_time"))
    return data


def week_bounds(week_start: date) -> tuple[str, str]:
    return week_start.isoformat(), (week_start + timedelta(days=6)).isoformat()


def require_schedule_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    if user.get("role_key") not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Only owner or payroll can edit schedules.")
    return user


def insert_shift_from_row(conn, row: dict[str, Any], shift_date: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO scheduled_shifts (employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?)
        """,
        (
            row.get("employee_id"),
            shift_date,
            row.get("start_time"),
            row.get("end_time"),
            row.get("position") or "Other",
            row.get("department"),
            int(row.get("break_minutes") or 0),
            row.get("notes"),
        ),
    )
    return int(cur.lastrowid)


@router.get("/schedules/employees")
def schedule_employees(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        cols = table_columns(conn, "employees")
        name_col = "full_name" if "full_name" in cols else "name"
        code_expr = "employee_code" if "employee_code" in cols else "'' AS employee_code"
        dept_expr = "department" if "department" in cols else "'' AS department"
        position_expr = "position" if "position" in cols else "'' AS position"
        status_expr = "employment_status" if "employment_status" in cols else "'active' AS employment_status"
        where = "WHERE COALESCE(employment_status, 'active') NOT IN ('inactive', 'terminated', 'resigned')" if "employment_status" in cols else ""
        rows = fetchall(
            conn,
            f"""
            SELECT id, {name_col} AS full_name, {code_expr}, {dept_expr}, {position_expr}, {status_expr}
            FROM employees
            {where}
            ORDER BY COALESCE(department, ''), {name_col}
            """,
        )
        return {"ok": True, "items": rows}
    finally:
        conn.close()


@router.get("/schedules/week")
def schedule_week(
    week_start: date = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    start, end = week_bounds(week_start)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        rows = fetchall(
            conn,
            """
            SELECT ss.*, e.full_name AS employee_name, e.employee_code, e.department AS employee_department
            FROM scheduled_shifts ss
            LEFT JOIN employees e ON e.id = ss.employee_id
            WHERE date(ss.shift_date) BETWEEN date(?) AND date(?)
            ORDER BY ss.shift_date, ss.start_time, COALESCE(e.full_name, 'Unassigned')
            """,
            (start, end),
        )
        return {"ok": True, "week_start": start, "week_end": end, "items": [clean_shift(row) for row in rows], "mode": "schedule_planned_hours_only_not_payroll"}
    finally:
        conn.close()


@router.post("/schedules/shifts")
def create_shift(
    payload: ShiftPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_schedule_editor(authorization, x_api_key)
    if payload.position not in POSITIONS:
        raise HTTPException(status_code=422, detail="Invalid position.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if payload.employee_id:
            employee = fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,))
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found.")
        conn.execute(
            """
            INSERT INTO scheduled_shifts (employee_id, shift_date, start_time, end_time, position, department, break_minutes, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload.employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, payload.break_minutes, payload.notes),
        )
        conn.commit()
        shift_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (shift_id,)) or {}
        return {"ok": True, "shift": clean_shift(row), "mode": "planned_schedule_only"}
    finally:
        conn.close()


@router.post("/schedules/shifts/{shift_id}/delete")
def delete_shift(
    shift_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_schedule_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        row = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (shift_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Shift not found.")
        conn.execute("DELETE FROM scheduled_shifts WHERE id=?", (shift_id,))
        conn.commit()
        return {"ok": True, "deleted_shift_id": shift_id, "mode": "planned_shift_deleted_not_payroll"}
    finally:
        conn.close()


@router.post("/schedules/shifts/{shift_id}/duplicate")
def duplicate_shift(
    shift_id: int,
    payload: DuplicateShiftPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_schedule_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        row = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (shift_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Shift not found.")
        target_date = (payload.shift_date.isoformat() if payload.shift_date else str(row.get("shift_date")))
        new_id = insert_shift_from_row(conn, row, target_date)
        conn.commit()
        copied = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (new_id,)) or {}
        return {"ok": True, "shift": clean_shift(copied), "mode": "planned_shift_duplicated_not_payroll"}
    finally:
        conn.close()


@router.post("/schedules/copy-week")
def copy_week(
    payload: CopyWeekPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_schedule_editor(authorization, x_api_key)
    source_start, source_end = week_bounds(payload.from_week_start)
    target_start = payload.to_week_start
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        rows = fetchall(
            conn,
            """
            SELECT * FROM scheduled_shifts
            WHERE date(shift_date) BETWEEN date(?) AND date(?)
            ORDER BY shift_date, start_time, id
            """,
            (source_start, source_end),
        )
        new_ids: list[int] = []
        for row in rows:
            source_date = datetime.fromisoformat(f"{row['shift_date']}T00:00:00").date()
            day_offset = (source_date - payload.from_week_start).days
            target_date = (target_start + timedelta(days=day_offset)).isoformat()
            new_ids.append(insert_shift_from_row(conn, row, target_date))
        conn.commit()
        return {"ok": True, "copied": len(new_ids), "new_shift_ids": new_ids, "mode": "planned_week_copied_not_payroll"}
    finally:
        conn.close()
