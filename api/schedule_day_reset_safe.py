from __future__ import annotations

from datetime import date, timedelta
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
    clear_reason: str | None = None
    confirmation: str | None = None


def _date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def ensure_marker_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_day_markers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,
            marker_type TEXT NOT NULL DEFAULT 'Rest Day',
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id, work_date, marker_type)
        )
        """
    )
    conn.commit()


def _active_leave_rows(conn, employee_id: int, work_date: str) -> list[dict[str, Any]]:
    return fetchall(
        conn,
        """
        SELECT * FROM leave_requests
        WHERE employee_id=? AND date(?) BETWEEN date(start_date) AND date(end_date)
          AND lower(COALESCE(status,'')) NOT IN ('rejected','declined','cancelled','canceled','void')
        ORDER BY id
        """,
        (employee_id, work_date),
    )


def _split_or_shrink_leave(conn, row: dict[str, Any], selected: date, actor: str | None, stamp: str) -> None:
    start = _date(row["start_date"])
    end = _date(row["end_date"])
    total_days = (end - start).days + 1
    stored_days = float(row.get("days") or total_days)
    if start == end:
        conn.execute("UPDATE leave_requests SET status='Cancelled', reviewed_by=?, reviewed_at=? WHERE id=?", (actor, stamp, row["id"]))
        return
    if abs(stored_days - total_days) > 0.001:
        raise HTTPException(status_code=409, detail="Multi-day fractional leave must be edited from HR leave requests.")
    if selected == start:
        conn.execute("UPDATE leave_requests SET start_date=?, days=?, reviewed_by=?, reviewed_at=? WHERE id=?", ((start + timedelta(days=1)).isoformat(), stored_days - 1, actor, stamp, row["id"]))
        return
    if selected == end:
        conn.execute("UPDATE leave_requests SET end_date=?, days=?, reviewed_by=?, reviewed_at=? WHERE id=?", ((end - timedelta(days=1)).isoformat(), stored_days - 1, actor, stamp, row["id"]))
        return
    left_start = start
    left_end = selected - timedelta(days=1)
    right_start = selected + timedelta(days=1)
    right_end = end
    left_days = (left_end - left_start).days + 1
    right_days = (right_end - right_start).days + 1
    conn.execute("UPDATE leave_requests SET end_date=?, days=?, reviewed_by=?, reviewed_at=? WHERE id=?", (left_end.isoformat(), left_days, actor, stamp, row["id"]))
    conn.execute(
        """
        INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, reviewed_by, reviewed_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, 'Approved'), ?, ?, ?, ?)
        """,
        (row["employee_id"], row["leave_type_id"], right_start.isoformat(), right_end.isoformat(), right_days, row.get("paid") or 0, row.get("status") or "Approved", row.get("reason"), actor, stamp, stamp),
    )


@router.post("/schedules/day/reset")
def reset_day(payload: ResetDayPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    clear_reason = (payload.clear_reason or "").strip()
    confirmation = (payload.confirmation or "").strip()
    if len(clear_reason) < 10:
        raise HTTPException(status_code=422, detail="Clear Day reason must be at least 10 characters.")
    if confirmation != "CLEAR DAY":
        raise HTTPException(status_code=422, detail="Type CLEAR DAY to confirm clearing this employee day.")
    work_date = payload.work_date.isoformat()
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        ensure_marker_schema(conn)
        if not employee_exists(conn, payload.employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        before = {
            "shifts": fetchall(conn, "SELECT * FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?)", (payload.employee_id, work_date)),
            "time_logs": fetchall(conn, "SELECT * FROM time_logs WHERE employee_id=? AND date(work_date)=date(?)", (payload.employee_id, work_date)),
            "leave_requests": _active_leave_rows(conn, payload.employee_id, work_date),
            "markers": fetchall(conn, "SELECT * FROM schedule_day_markers WHERE employee_id=? AND date(work_date)=date(?)", (payload.employee_id, work_date)),
        }
        stamp = now_iso()
        conn.execute("DELETE FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?)", (payload.employee_id, work_date))
        conn.execute("DELETE FROM time_logs WHERE employee_id=? AND date(work_date)=date(?)", (payload.employee_id, work_date))
        for row in before["leave_requests"]:
            _split_or_shrink_leave(conn, row, payload.work_date, user.get("display_name"), stamp)
        conn.execute("UPDATE schedule_day_markers SET active=0, updated_by=?, updated_at=? WHERE employee_id=? AND date(work_date)=date(?)", (user.get("display_name"), stamp, payload.employee_id, work_date))
        after = {
            "shifts": fetchall(conn, "SELECT * FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?)", (payload.employee_id, work_date)),
            "time_logs": fetchall(conn, "SELECT * FROM time_logs WHERE employee_id=? AND date(work_date)=date(?)", (payload.employee_id, work_date)),
            "leave_requests": _active_leave_rows(conn, payload.employee_id, work_date),
            "markers": fetchall(conn, "SELECT * FROM schedule_day_markers WHERE employee_id=? AND date(work_date)=date(?)", (payload.employee_id, work_date)),
        }
        log_schedule_change(
            conn,
            change_type="reset_day",
            entity_type="employee_day",
            entity_id=payload.employee_id,
            employee_id=payload.employee_id,
            work_date=work_date,
            before=before,
            after={**after, "clear_reason": clear_reason, "confirmation": "CLEAR DAY"},
            changed_by=user.get("display_name"),
        )
        conn.commit()
        return {"ok": True, "message": "Day cleared."}
    finally:
        conn.close()
