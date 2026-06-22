from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.main import current_user_from_token, require_api_key
from api.schedule_change_log import ensure_schedule_change_log_schema, log_schedule_change
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

POSITIONS = {"Receptionist", "Cook", "Barista", "Bartender", "Security", "Housekeeper", "Other"}


class ShiftPayload(BaseModel):
    employee_id: int | None = None
    shift_date: date
    start_time: str
    end_time: str
    position: str = "Other"
    department: str | None = None
    break_minutes: int = 60
    notes: str | None = None


class MoveShiftPayload(BaseModel):
    shift_date: date


class DuplicateShiftPayload(BaseModel):
    shift_date: date | None = None


class CopyWeekPayload(BaseModel):
    from_week_start: date
    to_week_start: date


class DaySchedulePayload(BaseModel):
    shift_id: int | None = None
    employee_id: int | None = None
    shift_date: date
    start_time: str
    end_time: str
    position: str = "Other"
    department: str | None = None
    break_minutes: int = 60
    notes: str | None = None


class DayActualPayload(BaseModel):
    employee_id: int
    shift_date: date
    actual_in: str | None = None
    actual_out: str | None = None
    attendance_status: str = "Pending"
    approved_ot_hours: float = 0
    notes: str | None = None


class DayLeavePayload(BaseModel):
    employee_id: int
    shift_date: date
    leave_kind: str = "None"
    leave_days: float = Field(default=1, gt=0)
    leave_hours: float | None = Field(default=None, ge=0)
    reason: str | None = None
    notice_given_at: str | None = None
    notice_timing: str | None = None
    evidence_ref: str | None = None


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def minutes_late_from_times(start_time: str | None, actual_in: str | None) -> int | None:
    if not start_time or not actual_in:
        return None
    try:
        start_h, start_m = [int(part) for part in str(start_time).split(":")[:2]]
        in_h, in_m = [int(part) for part in str(actual_in).split(":")[:2]]
    except Exception:
        return None
    scheduled_minutes = start_h * 60 + start_m
    actual_minutes = in_h * 60 + in_m
    diff = actual_minutes - scheduled_minutes
    return diff if diff > 0 else 0


def attendance_status_from_schedule(start_time: str | None, actual_in: str | None, fallback: str = "Pending") -> str:
    minutes = minutes_late_from_times(start_time, actual_in)
    if minutes is None:
        return fallback
    if minutes <= 0:
        return "ON-TIME"
    if minutes <= 5:
        return "Grace Period"
    if minutes > 30:
        return "Partial Absence"
    return "LATE"


def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def ensure_column(conn, table: str, column: str, definition: str) -> None:
    if column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            position TEXT NOT NULL DEFAULT 'Other',
            department TEXT,
            break_minutes INTEGER NOT NULL DEFAULT 60,
            status TEXT NOT NULL DEFAULT 'Draft',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column(conn, "scheduled_shifts", "legacy_schedule_id", "INTEGER")
    ensure_column(conn, "scheduled_shifts", "source", "TEXT NOT NULL DEFAULT 'planned'")
