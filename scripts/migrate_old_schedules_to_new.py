#!/usr/bin/env python3
"""One-time legacy schedule migration.

Make a database backup first, then run from the repository root:

    python3 scripts/migrate_old_schedules_to_new.py

This copies rows from the legacy `schedules` table into `scheduled_shifts`
without deleting or changing the old table. It is safe to run more than once:
already migrated rows are skipped through `legacy_schedule_id`.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "staff_payroll.sqlite"

DATE_CANDIDATES = ["work_date", "shift_date", "date", "schedule_date"]
START_CANDIDATES = ["shift_start", "start_time", "time_in", "scheduled_in"]
END_CANDIDATES = ["shift_end", "end_time", "time_out", "scheduled_out"]
EMPLOYEE_CANDIDATES = ["employee_id"]
POSITION_CANDIDATES = ["position", "role"]
DEPARTMENT_CANDIDATES = ["department", "department_name"]
BREAK_CANDIDATES = ["break_minutes", "break_mins"]
NOTES_CANDIDATES = ["notes", "note"]


def db_path() -> Path:
    return Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()


def connect() -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        print(f"ERROR: Database not found: {path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({quote(table)})").fetchall()}


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def first(cols: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in cols:
            return candidate
    return None


def add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = columns(conn, table)
    if column not in existing:
        conn.execute(f"ALTER TABLE {quote(table)} ADD COLUMN {quote(column)} {definition}")


def ensure_scheduled_shifts(conn: sqlite3.Connection) -> None:
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
    add_column(conn, "scheduled_shifts", "legacy_schedule_id", "INTEGER")
    add_column(conn, "scheduled_shifts", "source", "TEXT NOT NULL DEFAULT 'planned'")
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


def clear_error(found: set[str]) -> None:
    print("ERROR: legacy schedules table is missing required columns.", file=sys.stderr)
    print(f"Found columns: {', '.join(sorted(found))}", file=sys.stderr)
    print(f"Date candidates: {', '.join(DATE_CANDIDATES)}", file=sys.stderr)
    print(f"Start candidates: {', '.join(START_CANDIDATES)}", file=sys.stderr)
    print(f"End candidates: {', '.join(END_CANDIDATES)}", file=sys.stderr)
    sys.exit(1)


def normalize_time(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[1]
    if " " in text:
        text = text.rsplit(" ", 1)[-1]
    return text[:5] if len(text) >= 5 else text


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text or None


def existing_legacy_ids(conn: sqlite3.Connection) -> set[int]:
    return {
        int(row[0])
        for row in conn.execute(
            "SELECT legacy_schedule_id FROM scheduled_shifts WHERE legacy_schedule_id IS NOT NULL"
        ).fetchall()
        if row[0] is not None
    }


def main() -> int:
    conn = connect()
    try:
        if not table_exists(conn, "schedules"):
            print("ERROR: legacy schedules table does not exist.", file=sys.stderr)
            return 1

        ensure_scheduled_shifts(conn)
        legacy_cols = columns(conn, "schedules")
        date_col = first(legacy_cols, DATE_CANDIDATES)
        start_col = first(legacy_cols, START_CANDIDATES)
        end_col = first(legacy_cols, END_CANDIDATES)
        if not date_col or not start_col or not end_col:
            clear_error(legacy_cols)

        employee_col = first(legacy_cols, EMPLOYEE_CANDIDATES)
        position_col = first(legacy_cols, POSITION_CANDIDATES)
        department_col = first(legacy_cols, DEPARTMENT_CANDIDATES)
        break_col = first(legacy_cols, BREAK_CANDIDATES)
        notes_col = first(legacy_cols, NOTES_CANDIDATES)

        rows = conn.execute(f"SELECT * FROM {quote('schedules')} ORDER BY id").fetchall()
        migrated_ids = existing_legacy_ids(conn)
        total = len(rows)
        inserted = 0
        skipped = 0
        invalid = 0

        for row in rows:
            legacy_id = int(row["id"])
            if legacy_id in migrated_ids:
                skipped += 1
                continue

            shift_date = normalize_date(row[date_col])
            start_time = normalize_time(row[start_col])
            end_time = normalize_time(row[end_col])
            if not shift_date or not start_time or not end_time:
                invalid += 1
                print(
                    f"Invalid row skipped: schedules.id={legacy_id} date={row[date_col]!r} start={row[start_col]!r} end={row[end_col]!r}",
                    file=sys.stderr,
                )
                continue

            break_minutes = row[break_col] if break_col else 60
            try:
                break_value = int(break_minutes or 0)
            except (TypeError, ValueError):
                break_value = 60

            conn.execute(
                """
                INSERT INTO scheduled_shifts (
                    employee_id, shift_date, start_time, end_time, position, department,
                    break_minutes, status, notes, legacy_schedule_id, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, ?, 'migrated')
                """,
                (
                    row[employee_col] if employee_col else None,
                    shift_date,
                    start_time,
                    end_time,
                    row[position_col] if position_col else "Other",
                    row[department_col] if department_col else None,
                    break_value,
                    row[notes_col] if notes_col else None,
                    legacy_id,
                ),
            )
            inserted += 1

        conn.commit()
        print(f"Database: {db_path()}")
        print(f"Total old rows: {total}")
        print(f"Inserted rows: {inserted}")
        print(f"Skipped rows: {skipped}")
        print(f"Invalid rows: {invalid}")
        return 1 if invalid else 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
