from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.payroll_drafts import must_be_payroll_user
from api.schedules import DayActualPayload, DaySchedulePayload, MoveShiftPayload
from api.schedules import POSITIONS, clean_shift, day_bundle, employee_exists
from api.schedules import ensure_schema, fetch_legacy_schedule_row, fetch_shift, fetch_time_log
from api.schedule_change_log import ensure_schedule_change_log_schema, log_schedule_change
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter()


def row_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def local_now(conn) -> str:
    return str(conn.execute("SELECT datetime('now','localtime')").fetchone()[0])


def ensure_history_schema(conn) -> None:
    ensure_schema(conn)
    ensure_schedule_change_log_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_schedule_ignores (
            legacy_schedule_id INTEGER PRIMARY KEY,
            ignored_by TEXT,
            ignored_at TEXT NOT NULL,
            reason TEXT
        )
        """
    )
    conn.commit()


def schedule_row(conn, shift_id: int) -> dict[str, Any] | None:
    return row_dict(fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (shift_id,)))


def time_log_row(conn, log_id: int) -> dict[str, Any] | None:
    return row_dict(fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (log_id,)))


def migrate_legacy_row(conn, legacy_id: int, actor: str | None) -> int:
    existing = fetchone(conn, "SELECT id FROM scheduled_shifts WHERE legacy_schedule_id=?", (legacy_id,))
    if existing:
        return int(existing["id"])
    legacy = fetch_legacy_schedule_row(conn, legacy_id)
    if not legacy:
        raise HTTPException(status_code=404, detail="Legacy schedule row not found.")
    employee_id = int(legacy.get("employee_id") or 0)
    position = str(legacy.get("position") or "Other")
    if position not in POSITIONS:
        position = "Other"
    ts = local_now(conn)
    cur = conn.execute(
        """
        INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes, legacy_schedule_id, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, ?, 'planned', ?, ?)
        """,
        (employee_id, str(legacy.get("shift_date"))[:10], str(legacy.get("start_time"))[:5], str(legacy.get("end_time"))[:5], position, legacy.get("department") or legacy.get("employee_department"), int(legacy.get("break_minutes") or 0), legacy.get("notes"), legacy_id, ts, ts),
    )
    shift_id = int(cur.lastrowid)
    log_schedule_change(conn, change_type="migrate_legacy_schedule", entity_type="scheduled_shift", entity_id=shift_id, employee_id=employee_id, work_date=str(legacy.get("shift_date"))[:10], before=None, after=schedule_row(conn, shift_id), changed_by=actor)
    return shift_id


@router.post("/schedules/day/scheduled")
def save_schedule_history(payload: DaySchedulePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    employee_id = payload.employee_id if payload.employee_id and payload.employee_id > 0 else None
    conn = get_conn(DB_PATH)
    try:
        ensure_history_schema(conn)
        if employee_id and not employee_exists(conn, employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        if payload.position not in POSITIONS:
            raise HTTPException(status_code=422, detail="Invalid position.")
        shift_id = payload.shift_id
        if shift_id and shift_id < 0:
            shift_id = migrate_legacy_row(conn, abs(shift_id), user.get("display_name"))
        before = schedule_row(conn, shift_id) if shift_id else None
        ts = local_now(conn)
        if shift_id:
            if not before:
                raise HTTPException(status_code=404, detail="Shift not found.")
            conn.execute(
                """
                UPDATE scheduled_shifts SET employee_id=?, shift_date=?, start_time=?, end_time=?, position=?, department=?, break_minutes=?, notes=?, updated_at=? WHERE id=?
                """,
                (employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, int(payload.break_minutes or 0), payload.notes, ts, shift_id),
            )
            change_type = "update_schedule"
        else:
            cur = conn.execute(
                """
                INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, 'planned', ?, ?)
                """,
                (employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, int(payload.break_minutes or 0), payload.notes, ts, ts),
            )
            shift_id = int(cur.lastrowid)
            change_type = "create_schedule"
        after = schedule_row(conn, int(shift_id))
        log_schedule_change(conn, change_type=change_type, entity_type="scheduled_shift", entity_id=int(shift_id), employee_id=employee_id, work_date=payload.shift_date.isoformat(), before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return day_bundle(conn, payload.shift_date.isoformat(), employee_id, int(shift_id)) | {"message": "Scheduled shift saved. Existing payroll runs were not changed."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/schedules/day/actual")
def save_actual_history(payload: DayActualPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    shift_date = payload.shift_date.isoformat()
    conn = get_conn(DB_PATH)
    try:
        ensure_history_schema(conn)
        if not employee_exists(conn, payload.employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        status_value = payload.attendance_status.strip() or "Pending"
        existing = fetch_time_log(conn, payload.employee_id, shift_date)
        before = time_log_row(conn, int(existing["id"])) if existing else None
        ts = local_now(conn)
        if existing:
            conn.execute(
                """
                UPDATE time_logs SET actual_in=?, actual_out=?, attendance_status=?, approved_ot_hours=?, reviewed_by=?, reviewed_at=?, notes=?, updated_at=? WHERE id=?
                """,
                (payload.actual_in or None, payload.actual_out or None, status_value, float(payload.approved_ot_hours or 0), user.get("display_name"), ts, payload.notes, ts, existing["id"]),
            )
            log_id = int(existing["id"])
            change_type = "update_actual"
        else:
            cur = conn.execute(
                """
                INSERT INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type, is_absent, detected_ot_hours, approved_ot_hours, ot_status, attendance_status, reviewed_by, reviewed_at, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'manual', 'Manual', 0, 0, ?, 'None', ?, ?, ?, ?, ?, ?)
                """,
                (payload.employee_id, shift_date, payload.actual_in or None, payload.actual_out or None, float(payload.approved_ot_hours or 0), status_value, user.get("display_name"), ts, payload.notes, ts, ts),
            )
            log_id = int(cur.lastrowid)
            change_type = "create_actual"
        after = time_log_row(conn, log_id)
        log_schedule_change(conn, change_type=change_type, entity_type="time_log", entity_id=log_id, employee_id=payload.employee_id, work_date=shift_date, before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return day_bundle(conn, shift_date, payload.employee_id) | {"message": "Actual attendance saved. Existing payroll runs were not changed."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/schedules/shifts/{shift_id}/move")
def move_shift_history(shift_id: int, payload: MoveShiftPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_history_schema(conn)
        if shift_id < 0:
            shift_id = migrate_legacy_row(conn, abs(shift_id), user.get("display_name"))
        before = schedule_row(conn, shift_id)
        if not before:
            raise HTTPException(status_code=404, detail="Shift not found.")
        conn.execute("UPDATE scheduled_shifts SET shift_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (payload.shift_date.isoformat(), shift_id))
        after = schedule_row(conn, shift_id)
        log_schedule_change(conn, change_type="move_schedule", entity_type="scheduled_shift", entity_id=shift_id, employee_id=int((after or {}).get("employee_id") or 0), work_date=payload.shift_date.isoformat(), before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return {"ok": True, "shift": clean_shift(after or {}), "mode": "historical_shift_moved_payroll_snapshot_unchanged"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
