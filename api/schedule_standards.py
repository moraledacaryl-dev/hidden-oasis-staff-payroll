from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from core.db import fetchall, fetchone


MAX_STANDARD_PAID_HOURS = 12.0


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def table_columns(conn, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(conn, table: str, column: str, definition: str) -> None:
    if table_exists(conn, table) and column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schedule_review_columns(conn) -> None:
    ensure_column(conn, "scheduled_shifts", "review_status", "TEXT")
    ensure_column(conn, "scheduled_shifts", "review_reason", "TEXT")
    ensure_column(conn, "scheduled_shifts", "reviewed_by", "TEXT")
    ensure_column(conn, "scheduled_shifts", "reviewed_at", "TEXT")
    ensure_column(conn, "scheduled_shifts", "approved_exception", "INTEGER NOT NULL DEFAULT 0")


def shift_interval(shift_date: str, start_time: str, end_time: str) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(f"{shift_date[:10]}T{start_time[:5]}")
    end = datetime.fromisoformat(f"{shift_date[:10]}T{end_time[:5]}")
    if end <= start:
        end += timedelta(days=1)
    return start, end


def paid_hours(shift: dict[str, Any]) -> float:
    try:
        start, end = shift_interval(
            str(shift.get("shift_date") or ""),
            str(shift.get("start_time") or ""),
            str(shift.get("end_time") or ""),
        )
    except Exception:
        return 0.0
    gross = (end - start).total_seconds() / 3600
    break_minutes = int(shift.get("break_minutes") or 0)
    return round(max(0.0, gross - max(0, break_minutes) / 60), 2)


def schedule_standard_issues(conn, shift: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    shift_id = int(shift.get("id") or 0)
    employee_id = int(shift.get("employee_id") or 0)
    shift_date = str(shift.get("shift_date") or "")[:10]
    start_time = str(shift.get("start_time") or "")[:5]
    end_time = str(shift.get("end_time") or "")[:5]

    if not employee_id:
        issues.append("Missing employee assignment.")
    if not shift_date:
        issues.append("Missing shift date.")
    if not start_time or not end_time:
        issues.append("Missing start or end time.")

    try:
        target_start, target_end = shift_interval(shift_date, start_time, end_time)
    except Exception:
        issues.append("Invalid shift time.")
        return issues

    hours = paid_hours(shift)
    if hours > MAX_STANDARD_PAID_HOURS:
        issues.append(f"Planned paid hours exceed standard limit: {hours:g}h.")

    if employee_id:
        nearby = fetchall(
            conn,
            """
            SELECT id, shift_date, start_time, end_time
            FROM scheduled_shifts
            WHERE employee_id=?
              AND COALESCE(status,'Draft') NOT IN ('Cancelled','Deleted','Rejected')
              AND date(shift_date) BETWEEN date(?,'-1 day') AND date(?,'+1 day')
            """,
            (employee_id, shift_date, shift_date),
        )
        for other in nearby:
            other_id = int(other.get("id") or 0)
            if other_id == shift_id:
                continue
            try:
                other_start, other_end = shift_interval(
                    str(other.get("shift_date") or ""),
                    str(other.get("start_time") or ""),
                    str(other.get("end_time") or ""),
                )
            except Exception:
                continue
            if target_start < other_end and other_start < target_end:
                issues.append(f"Overlaps another scheduled shift #{other_id}.")
                break

    if employee_id and table_exists(conn, "leave_requests"):
        leave = fetchone(
            conn,
            """
            SELECT lr.id, lr.status, lt.name AS leave_type_name
            FROM leave_requests lr
            LEFT JOIN leave_types lt ON lt.id=lr.leave_type_id
            WHERE lr.employee_id=?
              AND date(?) BETWEEN date(lr.start_date) AND date(lr.end_date)
              AND lower(COALESCE(lr.status,'')) NOT IN ('rejected','declined','cancelled','canceled','void')
            ORDER BY lr.id DESC
            LIMIT 1
            """,
            (employee_id, shift_date),
        )
        if leave:
            leave_name = leave.get("leave_type_name") or "leave"
            issues.append(f"Employee has overlapping {leave_name} request.")

    return issues


def set_schedule_review_state(conn, shift_id: int, changed_by: str | None = None) -> dict[str, Any]:
    ensure_schedule_review_columns(conn)
    shift = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (shift_id,))
    if not shift:
        return {"ok": False, "issues": ["Shift not found."]}

    status = str(shift.get("status") or "")
    if status in {"Cancelled", "Deleted", "Rejected"}:
        return {"ok": True, "issues": [], "status": status}

    issues = schedule_standard_issues(conn, shift)
    stamp = now_iso()

    if issues:
        conn.execute(
            """
            UPDATE scheduled_shifts
            SET status='Needs Review',
                review_status='Needs Review',
                review_reason=?,
                reviewed_by=NULL,
                reviewed_at=NULL,
                approved_exception=0,
                updated_at=?
            WHERE id=?
            """,
            ("; ".join(issues), stamp, shift_id),
        )
        return {"ok": True, "issues": issues, "status": "Needs Review"}

    conn.execute(
        """
        UPDATE scheduled_shifts
        SET status='Confirmed',
            review_status='OK',
            review_reason=NULL,
            reviewed_by=?,
            reviewed_at=?,
            approved_exception=0,
            updated_at=?
        WHERE id=?
        """,
        (changed_by, stamp, stamp, shift_id),
    )
    return {"ok": True, "issues": [], "status": "Confirmed"}
