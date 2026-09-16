from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header

from api.schedules import require_schedule_viewer
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter(prefix="/api/v1")


@router.get("/schedules/active-employees")
def active_schedule_employees(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Return only employees who may be assigned new/future work."""
    require_schedule_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        rows = fetchall(
            conn,
            """
            SELECT id, full_name, employee_code, department, position,
                   default_shift_start, default_shift_end, unpaid_break_minutes,
                   status AS employment_status
            FROM employees
            WHERE lower(COALESCE(status, 'active')) NOT IN
                  ('inactive', 'terminated', 'resigned', 'separated')
            ORDER BY COALESCE(department, ''), full_name
            """,
        )
        return {"ok": True, "items": rows}
    finally:
        conn.close()
