from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from api.main import current_user_from_token
from api.schedule_publication import ensure_schema as ensure_publication_schema
from api.staff_self_service import employee_for_user, require_staff_user
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class AcknowledgePayload(BaseModel):
    notes: str | None = None


@router.post("/me/schedules/week/{week_start}/acknowledge")
def acknowledge_my_schedule(
    week_start: str,
    payload: AcknowledgePayload,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_publication_schema(conn)
        employee = employee_for_user(conn, user)
        publication = fetchone(
            conn,
            "SELECT id FROM schedule_publications WHERE week_start=? AND status='Published'",
            (week_start,),
        )
        if not publication:
            raise HTTPException(status_code=404, detail="Published schedule week not found.")

        conn.execute(
            """
            INSERT INTO schedule_acknowledgements(
                week_start, employee_id, acknowledged_by, acknowledged_at, notes
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(week_start, employee_id)
            DO UPDATE SET acknowledged_by=excluded.acknowledged_by,
                          acknowledged_at=CURRENT_TIMESTAMP,
                          notes=excluded.notes
            """,
            (
                week_start,
                int(employee["id"]),
                employee.get("full_name") or user.get("display_name"),
                payload.notes,
            ),
        )
        conn.commit()
        return {"ok": True, "week_start": week_start, "message": "Schedule acknowledged."}
    finally:
        conn.close()
