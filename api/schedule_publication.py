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


def week_end_for_start(week_start: str) -> str:
    return (datetime.fromisoformat(str(week_start)[:10]).date() + timedelta(days=6)).isoformat()


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
        CREATE TABLE IF NOT EXISTS schedule_publication_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            source_shift_id INTEGER,
            employee_id INTEGER,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            position TEXT,
            department TEXT,
            break_minutes INTEGER NOT NULL DEFAULT 0,
            status TEXT,
            notes TEXT,
            source TEXT,
            published_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_snapshot_week ON schedule_publication_shifts(week_start)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_snapshot_employee ON schedule_publication_shifts(employee_id, shift_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_ack_week ON schedule_acknowledgements(week_start)")
    conn.commit()


def current_week_shifts(conn, week_start: str) -> list[dict[str, Any]]:
    week_end = week_end_for_start(week_start)
    return fetchall(
        conn,
        """
        SELECT id AS source_shift_id, employee_id, shift_date, start_time, end_time,
               COALESCE(position, 'Other') AS position, department,
               COALESCE(break_minutes, 0) AS break_minutes,
               COALESCE(status, 'Draft') AS status, notes,
               COALESCE(source, 'planned') AS source
        FROM scheduled_shifts
        WHERE date(shift_date) BETWEEN date(?) AND date(?)
          AND COALESCE(status, 'Draft') NOT IN ('Cancelled', 'Deleted')
        ORDER BY date(shift_date), start_time, employee_id, id
        """,
        (week_start, week_end),
    )


def snapshot_week_shifts(conn, week_start: str) -> list[dict[str, Any]]:
    return fetchall(
        conn,
        """
        SELECT source_shift_id, employee_id, shift_date, start_time, end_time,
               COALESCE(position, 'Other') AS position, department,
               COALESCE(break_minutes, 0) AS break_minutes,
               COALESCE(status, 'Draft') AS status, notes,
               COALESCE(source, 'planned') AS source
        FROM schedule_publication_shifts
        WHERE week_start=?
        ORDER BY date(shift_date), start_time, employee_id, source_shift_id
        """,
        (week_start,),
    )


def comparable_shift(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row.get("source_shift_id") or 0),
        int(row.get("employee_id") or 0),
        str(row.get("shift_date") or "")[:10],
        str(row.get("start_time") or "")[:5],
        str(row.get("end_time") or "")[:5],
        str(row.get("position") or "Other"),
        str(row.get("department") or ""),
        int(row.get("break_minutes") or 0),
        str(row.get("status") or "Draft"),
        str(row.get("notes") or ""),
        str(row.get("source") or "planned"),
    )


def has_pending_changes(conn, week_start: str) -> bool:
    publication = fetchone(conn, "SELECT id FROM schedule_publications WHERE week_start=? AND status='Published'", (week_start,))
    if not publication:
        return False
    current = [comparable_shift(row) for row in current_week_shifts(conn, week_start)]
    snapshot = [comparable_shift(row) for row in snapshot_week_shifts(conn, week_start)]
    return current != snapshot


def replace_snapshot(conn, week_start: str) -> None:
    conn.execute("DELETE FROM schedule_publication_shifts WHERE week_start=?", (week_start,))
    for row in current_week_shifts(conn, week_start):
        conn.execute(
            """
            INSERT INTO schedule_publication_shifts(
                week_start, source_shift_id, employee_id, shift_date, start_time,
                end_time, position, department, break_minutes, status, notes, source,
                published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                week_start,
                row.get("source_shift_id"),
                row.get("employee_id"),
                row.get("shift_date"),
                row.get("start_time"),
                row.get("end_time"),
                row.get("position"),
                row.get("department"),
                int(row.get("break_minutes") or 0),
                row.get("status"),
                row.get("notes"),
                row.get("source"),
            ),
        )


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
    require_user(authorization, x_api_key, {"owner", "payroll", "supervisor"})
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        publication = fetchone(conn, "SELECT * FROM schedule_publications WHERE week_start=?", (week_start,))
        pending = has_pending_changes(conn, week_start) if publication else False
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
        return {
            "ok": True,
            "week_start": week_start,
            "publication": publication,
            "has_pending_changes": pending,
            "display_status": "Changes Pending" if pending else (publication.get("status") if publication else "Draft"),
            "acknowledgements": acks,
        }
    finally:
        conn.close()

@router.post("/schedules/week/{week_start}/publish")
def publish_schedule(week_start: str, payload: PublishSchedulePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_user(authorization, x_api_key, {"owner", "payroll", "supervisor"})
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO schedule_publications(week_start, status, published_by, published_at, notes)
            VALUES (?, 'Published', ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(week_start)
            DO UPDATE SET status='Published', published_by=excluded.published_by,
                          published_at=CURRENT_TIMESTAMP, notes=excluded.notes
            """,
            (week_start, user.get("display_name"), payload.notes),
        )
        replace_snapshot(conn, week_start)
        conn.execute("DELETE FROM schedule_acknowledgements WHERE week_start=?", (week_start,))
        conn.commit()
        row = fetchone(conn, "SELECT * FROM schedule_publications WHERE week_start=?", (week_start,))
        return {"ok": True, "publication": row, "has_pending_changes": False, "display_status": "Published"}
    finally:
        conn.close()
