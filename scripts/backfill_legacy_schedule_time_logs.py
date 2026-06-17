#!/usr/bin/env python3
"""Backfill actual time logs from legacy schedules.

Use this once for old payroll periods where the legacy `schedules` table was the
only source of truth and scheduled time should be treated as actual worked time.

The script is intentionally conservative:
- reads only legacy `schedules`, not the newer `scheduled_shifts` table;
- skips rest-day rows;
- skips an employee/date if any non-rejected time log already exists;
- inserts approved manual-equivalent logs with actual_in/out equal to shift_start/end.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db import get_conn, now_iso  # noqa: E402
from core.schedule_source import legacy_schedule_rows  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill approved time logs from legacy schedules.")
    parser.add_argument("--start", help="Start date YYYY-MM-DD. Required unless --all is used.")
    parser.add_argument("--end", help="End date YYYY-MM-DD. Required unless --all is used.")
    parser.add_argument("--all", action="store_true", help="Use the full date range found in legacy schedules.")
    parser.add_argument("--employee-id", type=int, help="Limit to one employee id.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted without writing.")
    return parser.parse_args()


def validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def legacy_bounds(conn) -> tuple[str, str]:
    row = conn.execute("SELECT MIN(work_date), MAX(work_date) FROM schedules WHERE COALESCE(is_rest_day,0)=0").fetchone()
    if not row or not row[0] or not row[1]:
        raise SystemExit("No legacy schedule rows found.")
    return str(row[0]), str(row[1])


def has_existing_log(conn, employee_id: int, work_date: str) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM time_logs
        WHERE employee_id=?
          AND work_date=?
          AND COALESCE(attendance_status, 'Pending') != 'Rejected'
        LIMIT 1
        """,
        (employee_id, work_date),
    ).fetchone()
    return bool(row)


def main() -> None:
    args = parse_args()
    conn = get_conn()
    try:
        if args.all:
            start, end = legacy_bounds(conn)
        else:
            if not args.start or not args.end:
                raise SystemExit("Use --start YYYY-MM-DD --end YYYY-MM-DD, or use --all.")
            start = validate_date(args.start)
            end = validate_date(args.end)
        if end < start:
            raise SystemExit("End date cannot be before start date.")

        rows = legacy_schedule_rows(conn, start, end, args.employee_id)
        rows = [row for row in rows if not int(row.get("is_rest_day") or 0)]
        inserted = 0
        skipped = 0
        timestamp = now_iso()

        for row in rows:
            employee_id = int(row.get("employee_id") or 0)
            work_date = str(row.get("work_date") or "")
            shift_start = str(row.get("shift_start") or "")[:5]
            shift_end = str(row.get("shift_end") or "")[:5]
            if not employee_id or not work_date or not shift_start or not shift_end:
                skipped += 1
                continue
            if has_existing_log(conn, employee_id, work_date):
                skipped += 1
                continue
            inserted += 1
            if args.dry_run:
                print(f"DRY RUN insert employee={employee_id} date={work_date} {shift_start}-{shift_end}")
                continue
            conn.execute(
                """
                INSERT INTO time_logs(
                    employee_id, work_date, actual_in, actual_out,
                    source, verification_type, is_absent,
                    detected_ot_hours, approved_ot_hours, ot_status,
                    attendance_status, notes, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    employee_id,
                    work_date,
                    shift_start,
                    shift_end,
                    "legacy_schedule",
                    "Legacy Schedule",
                    0,
                    0,
                    0,
                    "None",
                    "Approved",
                    "Backfilled from legacy schedule; scheduled time treated as actual time for old payroll data.",
                    timestamp,
                    timestamp,
                ),
            )

        if not args.dry_run:
            conn.commit()
        print(f"Legacy schedule backfill complete. inserted={inserted} skipped={skipped} range={start}..{end}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
