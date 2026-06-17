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

from api.schedules import POSITIONS, ensure_schema, fetch_legacy_schedule_rows  # noqa: E402
from core.db import get_conn  # noqa: E402


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


def legacy_bounds(conn) -> tuple[str, str]:
    row = conn.execute("SELECT MIN(work_date), MAX(work_date) FROM schedules").fetchone()
    if not row or not row[0] or not row[1]:
        raise SystemExit("No legacy schedule rows found.")
    return str(row[0]), str(row[1])


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

        rows = fetch_legacy_schedule_rows(conn, start, end)
        inserted = 0
        skipped_invalid = 0
        skipped_existing = 0
        skipped_employee = 0
        for row in rows:
            legacy_id = abs(int(row.get("legacy_id") or row.get("id") or 0))
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
            department = row.get("department") or row.get("employee_department")
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
