from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Header, Query

from api.schedules import require_schedule_viewer
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter(prefix="/api/v1")


@router.get("/schedules/leave-statuses")
def leave_statuses(
    week_start: date = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    require_schedule_viewer(authorization, x_api_key)
    week_end = week_start + timedelta(days=6)
    conn = get_conn(DB_PATH)
    try:
        rows = fetchall(
            conn,
            """
            SELECT lr.id, lr.employee_id, lr.start_date, lr.end_date,
                   COALESCE(lt.name, 'Leave') AS leave_type_name,
                   COALESCE(lr.paid, 0) AS paid,
                   COALESCE(lr.status, 'Approved') AS status,
                   COALESCE(lr.days, 1) AS days,
                   lr.reason
            FROM leave_requests lr
            LEFT JOIN leave_types lt ON lt.id=lr.leave_type_id
            WHERE date(lr.start_date) <= date(?)
              AND date(lr.end_date) >= date(?)
              AND lower(COALESCE(lr.status, 'approved')) NOT IN
                  ('rejected','declined','cancelled','canceled','void')
            ORDER BY lr.employee_id, lr.start_date, lr.id
            """,
            (week_end.isoformat(), week_start.isoformat()),
        )
        items = []
        for row in rows:
            start = max(date.fromisoformat(str(row["start_date"])[:10]), week_start)
            end = min(date.fromisoformat(str(row["end_date"])[:10]), week_end)
            cursor = start
            while cursor <= end:
                items.append({**row, "work_date": cursor.isoformat()})
                cursor += timedelta(days=1)
        return {"ok": True, "items": items}
    finally:
        conn.close()
