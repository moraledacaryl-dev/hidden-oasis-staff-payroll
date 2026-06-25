from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header

from api.main import current_user_from_token
from api.schedule_publication import publication_for_date, week_start_for_date
from api.staff_self_service import my_self_service
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


@router.get("/me/published-self-service")
def published_self_service(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    data = my_self_service(user=user, x_api_key=x_api_key)
    conn = get_conn(DB_PATH)
    try:
        employee_id = int((data.get("employee") or {}).get("id") or 0)
        published_schedule = []
        publications: dict[str, dict[str, Any]] = {}
        for shift in data.get("schedule", []):
            publication = publication_for_date(conn, str(shift.get("shift_date")))
            if not publication:
                continue
            week_start = week_start_for_date(str(shift.get("shift_date")))
            acknowledgement = fetchone(
                conn,
                "SELECT acknowledged_at, acknowledged_by, notes FROM schedule_acknowledgements WHERE week_start=? AND employee_id=?",
                (week_start, employee_id),
            ) if employee_id else None
            publications[week_start] = {
                "week_start": week_start,
                "published_at": publication.get("published_at"),
                "published_by": publication.get("published_by"),
                "notes": publication.get("notes"),
                "acknowledged": bool(acknowledgement),
                "acknowledged_at": acknowledgement.get("acknowledged_at") if acknowledgement else None,
            }
            published_schedule.append({**shift, "week_start": week_start})
        data["schedule"] = published_schedule
        data["publications"] = list(publications.values())
        return data
    finally:
        conn.close()
