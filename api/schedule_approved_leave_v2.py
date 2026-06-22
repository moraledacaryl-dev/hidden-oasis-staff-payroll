from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.schedule_change_log import log_schedule_change
from api.schedules import (
    day_bundle,
    employee_exists,
    ensure_leave_type,
    ensure_schema,
    fetch_leave,
    fetch_time_log,
    now_iso,
    require_schedule_editor,
)
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

PAID_LEAVE_TYPES = {
    "SIL",
    "Sick Leave",
    "Vacation Leave",
    "Bereavement Leave",
    "Official Business",
    "Other Approved Absence",
}
APPROVED_LEAVE_TYPES = PAID_LEAVE_TYPES | {"Emergency Leave", "None"}


class ApprovedLeavePayload(BaseModel):
    employee_id: int
    shift_date: str
    leave_kind: str = "None"
    leave_days: float = Field(default=1, gt=0)
    leave_hours: float | None = Field(default=None, ge=0)
    reason: str | None = None
    notice_given_at: str | None = None
    notice_timing: str | None = None
    evidence_ref: str | None = None


@router.post("/schedules/day/approved-leave")
def save_approved_leave(
    payload: ApprovedLeavePayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    leave_kind = payload.leave_kind.strip() or "None"
    if leave_kind not in APPROVED_LEAVE_TYPES:
        raise HTTPException(status_code=422, detail="Invalid approved leave type.")

    shift_date = payload.shift_date
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not employee_exists(conn, payload.employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")

        timestamp = now_iso()
        existing_log = fetch_time_log(conn, payload.employee_id, shift_date)
        existing_leave = fetch_leave(conn, payload.employee_id, shift_date)
        existing_shifts = fetchall(
            conn,
            "SELECT * FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?)",
            (payload.employee_id, shift_date),
        )
        before = {
            "time_log": dict(existing_log) if existing_log else None,
            "leave": dict(existing_leave) if existing_leave else None,
            "scheduled_shifts": existing_shifts,
        }

        if leave_kind == "None":
            if existing_leave:
                conn.execute(
                    "UPDATE leave_requests SET status='Cancelled', reviewed_by=?, reviewed_at=? WHERE id=?",
                    (user.get("display_name"), timestamp, existing_leave["id"]),
                )
            if existing_log:
                conn.execute(
                    "UPDATE time_logs SET is_absent=0, absence_type=NULL, notice_given_at=NULL, notice_timing=NULL, evidence_ref=NULL, updated_at=? WHERE id=?",
                    (timestamp, existing_log["id"]),
                )
            after = {"time_log": fetch_time_log(conn, payload.employee_id, shift_date), "leave": None}
            log_schedule_change(
                conn,
                change_type="clear_leave",
                entity_type="leave_request",
                entity_id=int(existing_leave["id"]) if existing_leave else None,
                employee_id=payload.employee_id,
                work_date=shift_date,
                before=before,
                after=after,
                changed_by=user.get("display_name"),
            )
            conn.commit()
            return day_bundle(conn, shift_date, payload.employee_id) | {"message": "Leave cleared."}

        conn.execute(
            "DELETE FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?)",
            (payload.employee_id, shift_date),
        )

        paid = 1 if leave_kind in PAID_LEAVE_TYPES else 0
        leave_type_id = ensure_leave_type(conn, leave_kind, paid)
        leave_days = float(payload.leave_days or 1)

        if existing_leave:
            conn.execute(
                """
                UPDATE leave_requests
                SET leave_type_id=?, start_date=?, end_date=?, days=?, paid=?, status='Approved',
                    reason=?, reviewed_by=?, reviewed_at=?
                WHERE id=?
                """,
                (
                    leave_type_id,
                    shift_date,
                    shift_date,
                    leave_days,
                    paid,
                    payload.reason,
                    user.get("display_name"),
                    timestamp,
                    existing_leave["id"],
                ),
            )
            leave_id = int(existing_leave["id"])
        else:
            cursor = conn.execute(
                """
                INSERT INTO leave_requests(
                    employee_id, leave_type_id, start_date, end_date, days, paid,
                    status, reason, reviewed_by, reviewed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'Approved', ?, ?, ?, ?)
                """,
                (
                    payload.employee_id,
                    leave_type_id,
                    shift_date,
                    shift_date,
                    leave_days,
                    paid,
                    payload.reason,
                    user.get("display_name"),
                    timestamp,
                    timestamp,
                ),
            )
            leave_id = int(cursor.lastrowid)

        if existing_log:
            conn.execute(
                """
                UPDATE time_logs
                SET actual_in=NULL, actual_out=NULL, is_absent=0, absence_type=NULL,
                    detected_ot_hours=0, approved_ot_hours=0, ot_status='None',
                    attendance_status='Approved', reviewed_by=?, reviewed_at=?,
                    notes=?, notice_given_at=?, notice_timing=?, evidence_ref=?, updated_at=?
                WHERE id=?
                """,
                (
                    user.get("display_name"),
                    timestamp,
                    payload.reason,
                    payload.notice_given_at,
                    payload.notice_timing or None,
                    payload.evidence_ref,
                    timestamp,
                    existing_log["id"],
                ),
            )
            log_id = int(existing_log["id"])
        else:
            cursor = conn.execute(
                """
                INSERT INTO time_logs(
                    employee_id, work_date, source, verification_type, is_absent,
                    absence_type, detected_ot_hours, approved_ot_hours, ot_status,
                    attendance_status, reviewed_by, reviewed_at, notes,
                    notice_given_at, notice_timing, evidence_ref, created_at, updated_at
                ) VALUES (?, ?, 'manual', 'Manual', 0, NULL, 0, 0, 'None',
                          'Approved', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.employee_id,
                    shift_date,
                    user.get("display_name"),
                    timestamp,
                    payload.reason,
                    payload.notice_given_at,
                    payload.notice_timing or None,
                    payload.evidence_ref,
                    timestamp,
                    timestamp,
                ),
            )
            log_id = int(cursor.lastrowid)

        after = {
            "time_log": dict(fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (log_id,)) or {}),
            "leave": dict(fetchone(conn, "SELECT * FROM leave_requests WHERE id=?", (leave_id,)) or {}),
            "scheduled_shifts": [],
        }
        log_schedule_change(
            conn,
            change_type="update_leave" if existing_leave else "create_leave",
            entity_type="leave_request",
            entity_id=leave_id,
            employee_id=payload.employee_id,
            work_date=shift_date,
            before=before,
            after=after,
            changed_by=user.get("display_name"),
        )
        conn.commit()
        return day_bundle(conn, shift_date, payload.employee_id) | {"message": f"{leave_kind} saved."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
