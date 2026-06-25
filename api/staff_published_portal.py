from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header

from api.main import current_user_from_token
from api.schedule_publication import publication_for_date
from api.staff_self_service import my_self_service
from core.db import DB_PATH, get_conn

router = APIRouter(prefix="/api/v1")


@router.get("/me/published-self-service")
def published_self_service(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    data = my_self_service(user=user, x_api_key=x_api_key)
    conn = get_conn(DB_PATH)
    try:
        data["schedule"] = [
            shift
            for shift in data.get("schedule", [])
            if publication_for_date(conn, str(shift.get("shift_date")))
        ]
        return data
    finally:
        conn.close()
