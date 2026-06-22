from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.schedule_change_log import log_schedule_change
from api.schedules import employee_exists, ensure_schema, now_iso, require_schedule_editor
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter(prefix="/api/v1")


class ResetDayPayload(BaseModel):
    employee_id: int
    work_date: date


@router.post("/schedules/day/reset")
def reset_day(
    payload: ResetDayPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    work_date = payload.work_date.isoformat()
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not employee_exists(conn, payload.employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")

        before = {
            "shifts": fetchall(conn, "SELECT * FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?)", (payload.employee_id, work_date)),
            "time_logs": fetchall(conn, "SELECT * FROM time_logs WHERE employee_id=? AND date(work_date)=date(?)", (payload.employee_id, work_date)),
            "leave_requests": fetchall(conn, "SELECT * FROM leave_requests WHERE employee_id=? AND date(?) BETWEEN date(start_date) AND date(end_date)", (payload.employee_id, work_date)),
            "markers": fetchall(conn, "SELECT * FROM schedule_day_markers WHERE employee_id=? AND date(work_date)=date(?)", (payload.employee_id, work_date)),
        }
        stamp = now_iso()

        conn.execute(
            "UPDATE scheduled_shifts SET status='Cleared', updated_at=? WHERE employee_id=? AND date(shift_date)=date(?)",
            (stamp, payload.employee_id, work_date),
        )
        conn.execute(
            """
            UPDATE time_logs
            SET actual_in=NULL, actual_out=NULL, is_absent=0, absence_type=NULL,
                detected_ot_hours=0, approved_ot_hours=0, ot_status='None',
                attendance_status='Cleared', notes=NULL, notice_given_at=NULL,
                notice_timing=NULL, evidence_ref=NULL, updated_at=?
            WHERE employee_id=? AND date(work_date)=date(?)
            """,
            (stamp, payload.employee_id, work_date),
        )
        conn.execute(
            """
            UPDATE leave_requests
            SET status='Cancelled', reviewed_by=?, reviewed_at=?
            WHERE employee_id=? AND date(?) BETWEEN date(start_date) AND date(end_date)
              AND lower(COALESCE(status,'')) NOT IN ('rejected','declined','cancelled','canceled','void')
            """,
            (user.get("display_name"), stamp, payload.employee_id, work_date),
        )
        conn.execute(
            """
            UPDATE schedule_day_markers
            SET active=0, updated_by=?, updated_at=?
            WHERE employee_id=? AND date(work_date)=date(?)
            """,
            (user.get("display_name"), stamp, payload.employee_id, work_date),
        )

        log_schedule_change(
            conn,
            change_type="reset_employee_day",
            entity_type="employee_day",
            entity_id=None,
            employee_id=payload.employee_id,
            work_date=work_date,
            before=before,
            after={"state": "empty"},
            changed_by=user.get("display_name"),
        )
        conn.commit()
        return {"ok": True, "message": "Day cleared. Choose Add shift, Rest day, or Leave again."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
