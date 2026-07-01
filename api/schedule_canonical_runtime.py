from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, Query

from api.schedules import clean_shift, ensure_schema, require_schedule_viewer, week_bounds
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter(prefix="/api/v1")


@router.get("/schedules/week")
def schedule_week(
    week_start: date = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Return the editable schedule board without legacy schedule overlays."""
    require_schedule_viewer(authorization, x_api_key)
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
        items = [clean_shift({**row, "source": row.get("source") or "planned", "movable": True}) for row in rows]
        return {"ok": True, "week_start": start, "week_end": end, "items": items, "mode": "canonical_scheduled_shifts_only"}
    finally:
        conn.close()
