from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.schedule_change_log import log_schedule_change
from api.schedule_day_reset_safe import _split_or_shrink_leave
from api.schedule_validation import validate_day_editor_leave_fraction, validate_positive_employee_id
from api.schedules import (
    DAY_EDITOR_ABSENCE_TYPES,
    DAY_EDITOR_LEAVE_TYPES,
    day_bundle,
    employee_exists,
    ensure_leave_type,
    ensure_schema,
    fetch_shift,
    fetch_time_log,
    hours_for_shift,
    now_iso,
    require_schedule_editor,
)
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

DAY_EDITOR_PAID_LEAVE_TYPES = DAY_EDITOR_LEAVE_TYPES | {"SIL"}
DAY_EDITOR_ALLOWED_TYPES = DAY_EDITOR_PAID_LEAVE_TYPES | DAY_EDITOR_ABSENCE_TYPES


class DayLeavePayload(BaseModel):
    employee_id: int
    shift_date: date
    leave_kind: str = "None"
    leave_days: float | None = None
    leave_hours: float | None = None
    reason: str | None = None
    notice_given_at: str | None = None
    notice_timing: str | None = None
    evidence_ref: str | None = None


def _active_leave_covering(conn: Any, employee_id: int, shift_date: str) -> dict[str, Any] | None:
    return fetchone(
        conn,
        """
        SELECT * FROM leave_requests
        WHERE employee_id=?
          AND start_date <= ? AND end_date >= ?
          AND COALESCE(status, 'Approved') NOT IN ('Rejected','Declined','Cancelled','Canceled','Void','Voided')
        ORDER BY id DESC
        LIMIT 1
        """,
        (employee_id, shift_date, shift_date),
    )


def _remove_selected_day_from_existing_leave(conn: Any, employee_id: int, selected_date: date, actor: str | None, timestamp: str) -> None:
    existing = _active_leave_covering(conn, employee_id, selected_date.isoformat())
    if existing:
        _split_or_shrink_leave(conn, existing, selected_date, actor, timestamp)


@router.post("/schedules/day/leave")
def save_day_leave(payload: DayLeavePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    employee_id = validate_positive_employee_id(payload.employee_id)
    shift_date = payload.shift_date.isoformat()
    leave_kind = payload.leave_kind.strip() or "None"
    if leave_kind not in DAY_EDITOR_ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail="Invalid leave or absence type.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not employee_id or not employee_exists(conn, employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        shift = fetch_shift(conn, None, employee_id, shift_date)
        scheduled_hours = None
        if shift:
            scheduled_hours = hours_for_shift(shift_date, str(shift.get("start_time") or "08:00")[:5], str(shift.get("end_time") or "17:00")[:5], int(shift.get("break_minutes") or 0))
        leave_days = validate_day_editor_leave_fraction(payload.leave_days, payload.leave_hours, scheduled_hours) if leave_kind in DAY_EDITOR_PAID_LEAVE_TYPES else 1.0
        timestamp = now_iso()
        actor = user.get("display_name")
        selected_date = payload.shift_date
        existing_log = fetch_time_log(conn, employee_id, shift_date)
        before = dict(existing_log) if existing_log else None
        log_id = None

        # Remove only the selected date from any covering leave first. This prevents the day editor
        # from truncating a multi-day leave and prevents paid leave from remaining active after the
        # user switches the same day to AWOL, another absence, or None.
        _remove_selected_day_from_existing_leave(conn, employee_id, selected_date, actor, timestamp)

        if leave_kind == "None":
            if existing_log:
                conn.execute("UPDATE time_logs SET is_absent=0, absence_type=NULL, updated_at=? WHERE id=?", (timestamp, existing_log["id"]))
                log_id = int(existing_log["id"])
        else:
            attendance_status = "Needs Review" if leave_kind in {"Unexcused Absence", "AWOL"} else "Approved"
            notice_given_at = None if leave_kind == "AWOL" else payload.notice_given_at
            notice_timing = "No notice" if leave_kind == "AWOL" else (payload.notice_timing or None)
            if existing_log:
                conn.execute("UPDATE time_logs SET is_absent=1, absence_type=?, attendance_status=?, reviewed_by=?, reviewed_at=?, notes=?, notice_given_at=?, notice_timing=?, evidence_ref=?, updated_at=? WHERE id=?", (leave_kind, attendance_status, actor, timestamp, payload.reason, notice_given_at, notice_timing, payload.evidence_ref, timestamp, existing_log["id"]))
                log_id = int(existing_log["id"])
            else:
                cur = conn.execute("INSERT INTO time_logs(employee_id, work_date, source, verification_type, is_absent, absence_type, detected_ot_hours, approved_ot_hours, ot_status, attendance_status, reviewed_by, reviewed_at, notes, notice_given_at, notice_timing, evidence_ref, created_at, updated_at) VALUES (?, ?, 'manual', 'Manual', 1, ?, 0, 0, 'None', ?, ?, ?, ?, ?, ?, ?, ?, ?)", (employee_id, shift_date, leave_kind, attendance_status, actor, timestamp, payload.reason, notice_given_at, notice_timing, payload.evidence_ref, timestamp, timestamp))
                log_id = int(cur.lastrowid)
            if leave_kind in DAY_EDITOR_PAID_LEAVE_TYPES:
                paid = 0 if leave_kind == "Emergency Leave" else 1
                leave_type_id = ensure_leave_type(conn, leave_kind, paid)
                conn.execute("INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, reviewed_by, reviewed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, 'Approved', ?, ?, ?, ?)", (employee_id, leave_type_id, shift_date, shift_date, leave_days, paid, payload.reason, actor, timestamp, timestamp))
        if log_id:
            after = dict(fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (log_id,)) or {})
            log_schedule_change(conn, change_type="update_absence" if before else "create_absence", entity_type="time_log", entity_id=log_id, employee_id=employee_id, work_date=shift_date, before=before, after=after, changed_by=actor)
        conn.commit()
        return day_bundle(conn, shift_date, employee_id) | {"message": "Leave/absence saved."}
    finally:
        conn.close()
