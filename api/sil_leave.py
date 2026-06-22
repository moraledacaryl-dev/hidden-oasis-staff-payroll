from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from api.schedules import (
    DayLeavePayload,
    day_bundle,
    employee_exists,
    ensure_leave_type,
    ensure_schema,
    fetch_leave,
    fetch_time_log,
    now_iso,
    require_schedule_editor,
)
from api.schedule_change_log import log_schedule_change
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

SIL_ALIASES = {
    "sil",
    "service incentive leave",
    "service incentive leave (sil)",
    "sil (service incentive leave)",
}


def canonical_sil(value: str | None) -> bool:
    return " ".join(str(value or "").strip().lower().split()) in SIL_ALIASES


@router.post("/schedules/day/sil")
def save_sil_leave(
    payload: DayLeavePayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    user = require_schedule_editor(authorization, x_api_key)
    if not canonical_sil(payload.leave_kind):
        raise HTTPException(status_code=422, detail="Invalid SIL leave type.")

    shift_date = payload.shift_date.isoformat()
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not employee_exists(conn, payload.employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")

        timestamp = now_iso()
        existing_log = fetch_time_log(conn, payload.employee_id, shift_date)
        before_log = dict(existing_log) if existing_log else None

        if existing_log:
            conn.execute(
                """
                UPDATE time_logs
                SET is_absent=1,
                    absence_type='SIL',
                    attendance_status='Approved',
                    reviewed_by=?,
                    reviewed_at=?,
                    notes=?,
                    notice_given_at=?,
                    notice_timing=?,
                    evidence_ref=?,
                    updated_at=?
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
                    employee_id, work_date, source, verification_type,
                    is_absent, absence_type, detected_ot_hours, approved_ot_hours,
                    ot_status, attendance_status, reviewed_by, reviewed_at,
                    notes, notice_given_at, notice_timing, evidence_ref,
                    created_at, updated_at
                ) VALUES (?, ?, 'manual', 'Manual', 1, 'SIL', 0, 0,
                          'None', 'Approved', ?, ?, ?, ?, ?, ?, ?, ?)
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

        leave_type_id = ensure_leave_type(conn, "SIL", 1)
        existing_leave = fetch_leave(conn, payload.employee_id, shift_date)
        before_leave = dict(existing_leave) if existing_leave else None
        if existing_leave:
            conn.execute(
                """
                UPDATE leave_requests
                SET leave_type_id=?, start_date=?, end_date=?, days=1,
                    paid=1, status='Approved', reason=?, reviewed_by=?, reviewed_at=?
                WHERE id=?
                """,
                (
                    leave_type_id,
                    shift_date,
                    shift_date,
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
                    employee_id, leave_type_id, start_date, end_date,
                    days, paid, status, reason, reviewed_by, reviewed_at, created_at
                ) VALUES (?, ?, ?, ?, 1, 1, 'Approved', ?, ?, ?, ?)
                """,
                (
                    payload.employee_id,
                    leave_type_id,
                    shift_date,
                    shift_date,
                    payload.reason,
                    user.get("display_name"),
                    timestamp,
                    timestamp,
                ),
            )
            leave_id = int(cursor.lastrowid)

        after_log = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (log_id,))
        after_leave = fetchone(conn, "SELECT * FROM leave_requests WHERE id=?", (leave_id,))
        log_schedule_change(
            conn,
            change_type="update_sil" if before_log or before_leave else "create_sil",
            entity_type="leave_request",
            entity_id=leave_id,
            employee_id=payload.employee_id,
            work_date=shift_date,
            before={"time_log": before_log, "leave": before_leave},
            after={"time_log": dict(after_log or {}), "leave": dict(after_leave or {})},
            changed_by=user.get("display_name"),
        )
        conn.commit()
        return day_bundle(conn, shift_date, payload.employee_id) | {
            "message": "SIL saved as paid Service Incentive Leave."
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
