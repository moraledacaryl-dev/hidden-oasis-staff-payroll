#!/usr/bin/env python3
"""Copy legacy schedule rows into scheduled_shifts so old schedules become editable.

This is different from the time-log backfill script. This script migrates the old
`schedules` rows into the newer editable `scheduled_shifts` table used by the
schedule page drag/drop and day editor.

Safety behavior:
- skips invalid rows without employee/date/start/end;
- skips rows already migrated by legacy_schedule_id;
- skips rows that already have the same employee/date/start/end in scheduled_shifts;
- does not delete old schedules;
- defaults to dry-run unless --apply is passed.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db import get_conn  # noqa: E402

POSITIONS = {"Receptionist", "Cook", "Barista", "Bartender", "Security", "Housekeeper", "Other"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy schedules into editable scheduled_shifts.")
    parser.add_argument("--start", help="Start date YYYY-MM-DD. Required unless --all is used.")
    parser.add_argument("--end", help="End date YYYY-MM-DD. Required unless --all is used.")
    parser.add_argument("--all", action="store_true", help="Use the full date range found in the legacy schedules table.")
    parser.add_argument("--employee-id", type=int, help="Limit to one employee id.")
    parser.add_argument("--apply", action="store_true", help="Actually write changes. Without this, it is a dry run.")
    return parser.parse_args()


def validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def table_columns(conn, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def first_existing(cols: set[str], names: list[str]) -> str | None:
    for name in names:
        if name in cols:
            return name
    return None


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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_shifts_date ON scheduled_shifts(shift_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_shifts_employee ON scheduled_shifts(employee_id)")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_shifts_legacy_schedule_id
        ON scheduled_shifts(legacy_schedule_id)
        WHERE legacy_schedule_id IS NOT NULL
        """
    )
    conn.commit()


def legacy_bounds(conn) -> tuple[str, str]:
    if not table_exists(conn, "schedules"):
        raise SystemExit("No legacy schedules table found.")
    cols = table_columns(conn, "schedules")
    date_col = first_existing(cols, ["work_date", "shift_date", "date", "schedule_date"])
    if not date_col:
        raise SystemExit("Legacy schedules table has no usable date column.")
    row = conn.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM schedules").fetchone()
    if not row or not row[0] or not row[1]:
        raise SystemExit("No legacy schedule rows found.")
    return str(row[0]), str(row[1])


def fetch_legacy_rows(conn, start: str, end: str) -> list[dict[str, Any]]:
    if not table_exists(conn, "schedules"):
        return []
    cols = table_columns(conn, "schedules")
    date_col = first_existing(cols, ["work_date", "shift_date", "date", "schedule_date"])
    start_col = first_existing(cols, ["shift_start", "start_time", "time_in", "scheduled_in"])
    end_col = first_existing(cols, ["shift_end", "end_time", "time_out", "scheduled_out"])
    if not date_col or not start_col or not end_col or "employee_id" not in cols:
        return []
    position_col = first_existing(cols, ["position", "role"])
    department_col = first_existing(cols, ["department", "department_name"])
    break_col = first_existing(cols, ["break_minutes", "break_mins", "unpaid_break_minutes"])
    notes_col = first_existing(cols, ["notes", "note"])
    select_cols = [
        "s.id AS legacy_id",
        "s.employee_id AS employee_id",
        f"s.{date_col} AS shift_date",
        f"s.{start_col} AS start_time",
        f"s.{end_col} AS end_time",
        f"s.{position_col} AS position" if position_col else "'Other' AS position",
        f"s.{department_col} AS department" if department_col else "NULL AS department",
        f"s.{break_col} AS break_minutes" if break_col else "60 AS break_minutes",
        f"s.{notes_col} AS notes" if notes_col else "NULL AS notes",
    ]
    cursor = conn.execute(
        f"""
        SELECT {', '.join(select_cols)}
        FROM schedules s
        WHERE date(s.{date_col}) BETWEEN date(?) AND date(?)
        ORDER BY s.{date_col}, s.{start_col}, s.id
        """,
        (start, end),
    )
    names = [description[0] for description in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def already_migrated(conn, legacy_id: int) -> bool:
    row = conn.execute(
        "SELECT id FROM scheduled_shifts WHERE legacy_schedule_id=? LIMIT 1",
        (legacy_id,),
    ).fetchone()
    return bool(row)


def duplicate_shift(conn, employee_id: int, shift_date: str, start_time: str, end_time: str) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM scheduled_shifts
        WHERE employee_id=?
          AND date(shift_date)=date(?)
          AND start_time=?
          AND end_time=?
        LIMIT 1
        """,
        (employee_id, shift_date, start_time, end_time),
    ).fetchone()
    return bool(row)


def clean_time(value: Any) -> str:
    return str(value or "")[:5]


def main() -> None:
    args = parse_args()
    dry_run = not args.apply
    conn = get_conn()
    try:
        ensure_schema(conn)
        if args.all:
            start, end = legacy_bounds(conn)
        else:
            if not args.start or not args.end:
                raise SystemExit("Use --start YYYY-MM-DD --end YYYY-MM-DD, or use --all.")
            start = validate_date(args.start)
            end = validate_date(args.end)
        if end < start:
            raise SystemExit("End date cannot be before start date.")

        rows = fetch_legacy_rows(conn, start, end)
        inserted = 0
        skipped_invalid = 0
        skipped_existing = 0
        skipped_employee = 0
        for row in rows:
            legacy_id = abs(int(row.get("legacy_id") or 0))
            employee_id = int(row.get("employee_id") or 0)
            shift_date = str(row.get("shift_date") or "")[:10]
            start_time = clean_time(row.get("start_time"))
            end_time = clean_time(row.get("end_time"))
            if args.employee_id and employee_id != args.employee_id:
                skipped_employee += 1
                continue
            if not legacy_id or not employee_id or not shift_date or not start_time or not end_time:
                skipped_invalid += 1
                continue
            if already_migrated(conn, legacy_id) or duplicate_shift(conn, employee_id, shift_date, start_time, end_time):
                skipped_existing += 1
                continue
            position = str(row.get("position") or "Other")
            if position not in POSITIONS:
                position = "Other"
            department = row.get("department")
            break_minutes = int(row.get("break_minutes") or 0)
            notes = row.get("notes")
            inserted += 1
            if dry_run:
                print(f"DRY RUN migrate legacy_id={legacy_id} employee={employee_id} date={shift_date} {start_time}-{end_time}")
                continue
            conn.execute(
                """
                INSERT INTO scheduled_shifts(
                    employee_id, shift_date, start_time, end_time, position,
                    department, break_minutes, status, notes, legacy_schedule_id, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, ?, 'planned')
                """,
                (employee_id, shift_date, start_time, end_time, position, department, break_minutes, notes, legacy_id),
            )
        if not dry_run:
            conn.commit()
        print(
            "Legacy schedule editable migration complete. "
            f"{'would_insert' if dry_run else 'inserted'}={inserted} "
            f"skipped_existing={skipped_existing} skipped_invalid={skipped_invalid} "
            f"skipped_employee={skipped_employee} range={start}..{end}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
