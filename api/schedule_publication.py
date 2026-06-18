from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

REASON_CATEGORIES = {
    "Staff request",
    "Emergency absence",
    "Coverage adjustment",
    "Management instruction",
    "Correction of error",
    "Weather / operational issue",
    "Other",
}


class PublishSchedulePayload(BaseModel):
    notes: str | None = None


class AcknowledgeSchedulePayload(BaseModel):
    notes: str | None = None


class PublishedChangeFields(BaseModel):
    change_reason: str | None = None
    change_note: str | None = None
    attachment_ref: str | None = None


def require_user(authorization: str | None, x_api_key: str | None, allowed: set[str]) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in allowed:
        raise HTTPException(status_code=403, detail="Schedule access denied.")
    return user


def week_start_for_date(value: str | date) -> str:
    if isinstance(value, date):
        d = value
    else:
        d = datetime.fromisoformat(str(value)[:10]).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'Published',
            published_by TEXT,
            published_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_acknowledgements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            acknowledged_by TEXT,
            acknowledged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            UNIQUE(week_start, employee_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_ack_week ON schedule_acknowledgements(week_start)")
    conn.commit()


def publication_for_date(conn, work_date: str | date) -> dict[str, Any] | None:
    ensure_schema(conn)
    return fetchone(conn, "SELECT * FROM schedule_publications WHERE week_start=? AND status='Published'", (week_start_for_date(work_date),))


def published_change_meta(payload: Any) -> dict[str, str | None]:
    return {
        "reason_category": getattr(payload, "change_reason", None),
        "reason_note": getattr(payload, "change_note", None),
        "attachment_ref": getattr(payload, "attachment_ref", None),
    }


def require_change_reason_if_published(conn, work_date: str | date, payload: Any) -> None:
    if not publication_for_date(conn, work_date):
        return
    reason = str(getattr(payload, "change_reason", "") or "").strip()
    note = str(getattr(payload, "change_note", "") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Published schedule changes require a reason.")
    if reason not in REASON_CATEGORIES:
        raise HTTPException(status_code=422, detail="Invalid published schedule change reason.")
    if reason == "Other" and not note:
        raise HTTPException(status_code=422, detail="Published schedule changes marked Other require a note.")


@router.get("/schedules/week/{week_start}/publication")
def get_schedule_publication(week_start: str, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_user(authorization, x_api_key, {"owner", "payroll", "supervisor", "staff"})
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        publication = fetchone(conn, "SELECT * FROM schedule_publications WHERE week_start=?", (week_start,))
        acks = fetchall(
            conn,
            """
            SELECT sa.*, e.full_name, e.employee_code, e.department, e.position
            FROM schedule_acknowledgements sa
            JOIN employees e ON e.id=sa.employee_id
            WHERE sa.week_start=?
            ORDER BY e.full_name
            """,
            (week_start,),
        )
        return {"ok": True, "week_start": week_start, "publication": publication, "acknowledgements": acks}
    finally:
        conn.close()


@router.post("/schedules/week/{week_start}/publish")
def publish_schedule(week_start: str, payload: PublishSchedulePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_user(authorization, x_api_key, {"owner", "payroll"})
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO schedule_publications(week_start, status, published_by, published_at, notes)
            VALUES (?, 'Published', ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(week_start)
            DO UPDATE SET status='Published', published_by=excluded.published_by, published_at=CURRENT_TIMESTAMP, notes=excluded.notes
            """,
            (week_start, user.get("display_name"), payload.notes),
        )
        conn.commit()
        row = fetchone(conn, "SELECT * FROM schedule_publications WHERE week_start=?", (week_start,))
        return {"ok": True, "publication": row}
    finally:
        conn.close()


@router.post("/schedules/week/{week_start}/acknowledge")
def acknowledge_schedule(week_start: str, payload: AcknowledgeSchedulePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_user(authorization, x_api_key, {"owner", "payroll", "supervisor", "staff"})
    employee_id = user.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=422, detail="User is not linked to an employee record.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO schedule_acknowledgements(week_start, employee_id, acknowledged_by, acknowledged_at, notes)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(week_start, employee_id)
            DO UPDATE SET acknowledged_by=excluded.acknowledged_by, acknowledged_at=CURRENT_TIMESTAMP, notes=excluded.notes
            """,
            (week_start, int(employee_id), user.get("display_name"), payload.notes),
        )
        conn.commit()
        return {"ok": True, "message": "Schedule acknowledged."}
    finally:
        conn.close()
