from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Header, Query

from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter(prefix="/api/v1")


def week_bounds(week_start: date) -> tuple[str, str]:
    return week_start.isoformat(), (week_start + timedelta(days=6)).isoformat()


def require_schedule_viewer(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Schedule view requires owner, payroll, or supervisor role.")
    return user


@router.get("/schedules/actuals/week")
def schedule_actuals_week(
    week_start: date = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_schedule_viewer(authorization, x_api_key)
    start, end = week_bounds(week_start)
    conn = get_conn(DB_PATH)
    try:
        rows = fetchall(
            conn,
            """
            SELECT
                tl.id,
                tl.employee_id,
                tl.work_date,
                tl.actual_in,
                tl.actual_out,
                tl.attendance_status,
                tl.approved_ot_hours,
                tl.is_absent,
                tl.absence_type,
                tl.source,
                tl.verification_type,
                tl.notes,
                e.full_name AS employee_name
            FROM time_logs tl
            LEFT JOIN employees e ON e.id = tl.employee_id
            WHERE date(tl.work_date) BETWEEN date(?) AND date(?)
              AND COALESCE(tl.attendance_status, '') != 'Rejected'
            ORDER BY tl.work_date, e.full_name, tl.id DESC
            """,
            (start, end),
        )
        return {"ok": True, "week_start": start, "week_end": end, "items": rows, "mode": "actual_attendance_by_week"}
    finally:
        conn.close()
