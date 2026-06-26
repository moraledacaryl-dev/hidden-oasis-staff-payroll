from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from api.schedule_change_log import ensure_schedule_change_log_schema, log_schedule_change
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class RestDayPayload(BaseModel):
    employee_id: int
    work_date: date
    active: bool = True
    notes: str | None = None


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def require_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Only owner, payroll, or the General Manager can edit rest days.")
    return user


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_day_markers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,
            marker_type TEXT NOT NULL,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(employee_id, work_date, marker_type)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_day_markers_week ON schedule_day_markers(work_date, marker_type, active)")
    ensure_schedule_change_log_schema(conn)
    conn.commit()


def week_bounds(week_start: date) -> tuple[str, str]:
    return week_start.isoformat(), (week_start + timedelta(days=6)).isoformat()


@router.get("/schedules/rest-days")
def list_rest_days(
    week_start: date = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_editor(authorization, x_api_key)
    start, end = week_bounds(week_start)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        items = fetchall(
            conn,
            """
            SELECT m.*, e.full_name AS employee_name
            FROM schedule_day_markers m
            LEFT JOIN employees e ON e.id=m.employee_id
            WHERE m.marker_type='Rest Day'
              AND m.active=1
              AND date(m.work_date) BETWEEN date(?) AND date(?)
            ORDER BY m.work_date, e.full_name
            """,
            (start, end),
        )
        return {"ok": True, "week_start": start, "week_end": end, "items": items}
    finally:
        conn.close()


@router.post("/schedules/rest-days")
def save_rest_day(
    payload: RestDayPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = fetchone(conn, "SELECT id,full_name FROM employees WHERE id=?", (payload.employee_id,))
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found.")

        work_date = payload.work_date.isoformat()
        existing_shift = fetchone(
            conn,
            "SELECT id FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?) LIMIT 1",
            (payload.employee_id, work_date),
        )
        if payload.active and existing_shift:
            raise HTTPException(status_code=409, detail="Remove the scheduled shift before marking this day as a rest day.")

        existing = fetchone(
            conn,
            "SELECT * FROM schedule_day_markers WHERE employee_id=? AND work_date=? AND marker_type='Rest Day'",
            (payload.employee_id, work_date),
        )
        before = dict(existing) if existing else None
        stamp = now_iso()
        conn.execute(
            """
            INSERT INTO schedule_day_markers(
                employee_id,work_date,marker_type,notes,active,
                created_by,created_at,updated_by,updated_at
            ) VALUES(?,?,'Rest Day',?,?,?,?,?,?)
            ON CONFLICT(employee_id,work_date,marker_type) DO UPDATE SET
                notes=excluded.notes,
                active=excluded.active,
                updated_by=excluded.updated_by,
                updated_at=excluded.updated_at
            """,
            (
                payload.employee_id,
                work_date,
                payload.notes,
                1 if payload.active else 0,
                user.get("display_name"),
                stamp,
                user.get("display_name"),
                stamp,
            ),
        )
        after = fetchone(
            conn,
            "SELECT * FROM schedule_day_markers WHERE employee_id=? AND work_date=? AND marker_type='Rest Day'",
            (payload.employee_id, work_date),
        )
        log_schedule_change(
            conn,
            change_type="mark_rest_day" if payload.active else "clear_rest_day",
            entity_type="schedule_day_marker",
            entity_id=int(after["id"]) if after else None,
            employee_id=payload.employee_id,
            work_date=work_date,
            before=before,
            after=dict(after) if after else None,
            changed_by=user.get("display_name"),
        )
        conn.commit()
        return {
            "ok": True,
            "item": after,
            "message": "Rest day marked." if payload.active else "Rest day cleared.",
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
