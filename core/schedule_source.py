from __future__ import annotations

from typing import Any
import sqlite3

from .db import fetchall, fetchone


LEGACY_SCHEDULE_STATUSES = ("For Owner Review", "Approved", "Paid", "Locked")


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = fetchone(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return bool(row and int(row.get("c") or 0) > 0)


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def first_existing(cols: set[str], names: list[str]) -> str | None:
    for name in names:
        if name in cols:
            return name
    return None


def _normalize_schedule_row(row: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "employee_id": row.get("employee_id"),
        "work_date": str(row.get("work_date") or row.get("shift_date") or ""),
        "shift_start": str(row.get("shift_start") or row.get("start_time") or "00:00")[:5],
        "shift_end": str(row.get("shift_end") or row.get("end_time") or "00:00")[:5],
        "break_minutes": int(row.get("break_minutes") or 0),
        "department": row.get("department"),
        "is_rest_day": int(row.get("is_rest_day") or 0),
        "notes": row.get("notes"),
        "schedule_source": source,
    }


def scheduled_shift_rows(
    conn: sqlite3.Connection,
    period_start: str,
    period_end: str,
    employee_id: int | None = None,
) -> list[dict[str, Any]]:
    if not table_exists(conn, "scheduled_shifts"):
        return []
    params: list[Any] = [period_start, period_end]
    employee_filter = ""
    if employee_id is not None:
        employee_filter = " AND ss.employee_id=?"
        params.append(employee_id)
    rows = fetchall(
        conn,
        f"""
        SELECT
            ss.employee_id,
            ss.shift_date AS work_date,
            ss.start_time AS shift_start,
            ss.end_time AS shift_end,
            ss.break_minutes,
            ss.department,
            0 AS is_rest_day,
            ss.notes
        FROM scheduled_shifts ss
        WHERE ss.employee_id IS NOT NULL
          AND date(ss.shift_date) BETWEEN date(?) AND date(?)
          {employee_filter}
        ORDER BY ss.shift_date, ss.start_time, ss.id
        """,
        tuple(params),
    )
    return [_normalize_schedule_row(row, "scheduled_shifts") for row in rows]


def legacy_schedule_rows(
    conn: sqlite3.Connection,
    period_start: str,
    period_end: str,
    employee_id: int | None = None,
) -> list[dict[str, Any]]:
    cols = table_columns(conn, "schedules")
    date_col = first_existing(cols, ["work_date", "shift_date", "date", "schedule_date"])
    start_col = first_existing(cols, ["shift_start", "start_time", "time_in", "scheduled_in"])
    end_col = first_existing(cols, ["shift_end", "end_time", "time_out", "scheduled_out"])
    if not date_col or not start_col or not end_col or "employee_id" not in cols:
        return []

    break_col = first_existing(cols, ["break_minutes", "break_mins", "unpaid_break_minutes"])
    department_col = first_existing(cols, ["department", "department_name"])
    rest_col = first_existing(cols, ["is_rest_day", "rest_day"])
    notes_col = first_existing(cols, ["notes", "note"])
    break_expr = f"s.{break_col}" if break_col else "60"
    department_expr = f"s.{department_col}" if department_col else "NULL"
    rest_expr = f"s.{rest_col}" if rest_col else "0"
    notes_expr = f"s.{notes_col}" if notes_col else "NULL"
    params: list[Any] = [period_start, period_end]
    employee_filter = ""
    if employee_id is not None:
        employee_filter = " AND s.employee_id=?"
        params.append(employee_id)

    rows = fetchall(
        conn,
        f"""
        SELECT
            s.employee_id,
            s.{date_col} AS work_date,
            s.{start_col} AS shift_start,
            s.{end_col} AS shift_end,
            {break_expr} AS break_minutes,
            {department_expr} AS department,
            {rest_expr} AS is_rest_day,
            {notes_expr} AS notes
        FROM schedules s
        WHERE date(s.{date_col}) BETWEEN date(?) AND date(?)
          {employee_filter}
        ORDER BY s.{date_col}, s.{start_col}, s.id
        """,
        tuple(params),
    )
    return [_normalize_schedule_row(row, "legacy_schedules") for row in rows]


def trusted_schedule_rows(
    conn: sqlite3.Connection,
    period_start: str,
    period_end: str,
    employee_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return payroll schedule rows, preferring the editable scheduled_shifts table.

    Legacy schedules remain as a fallback only for employee/date pairs that have
    not been migrated or recreated in scheduled_shifts.
    """
    planned = scheduled_shift_rows(conn, period_start, period_end, employee_id)
    planned_keys = {(row["employee_id"], row["work_date"]) for row in planned}
    fallback = [
        row
        for row in legacy_schedule_rows(conn, period_start, period_end, employee_id)
        if (row["employee_id"], row["work_date"]) not in planned_keys
    ]
    return sorted(planned + fallback, key=lambda row: (str(row["work_date"]), str(row["shift_start"]), int(row["employee_id"] or 0)))


def trusted_scheduled_workdays(conn: sqlite3.Connection, period_start: str, period_end: str) -> list[dict[str, Any]]:
    rows = trusted_schedule_rows(conn, period_start, period_end)
    employee_ids = {int(row["employee_id"]) for row in rows if row.get("employee_id") is not None}
    if not employee_ids:
        return []
    placeholders = ",".join("?" for _ in employee_ids)
    employees = fetchall(
        conn,
        f"SELECT id, status FROM employees WHERE id IN ({placeholders})",
        tuple(sorted(employee_ids)),
    )
    active = {int(row["id"]) for row in employees if str(row.get("status") or "Active") not in {"Inactive", "Terminated"}}
    return [
        row
        for row in rows
        if int(row.get("employee_id") or 0) in active and not int(row.get("is_rest_day") or 0)
    ]
