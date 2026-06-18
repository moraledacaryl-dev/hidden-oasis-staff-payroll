#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(os.getenv("STAFF_PAYROLL_DB_PATH", "data/staff_payroll.sqlite"))


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def ensure_ignore_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_schedule_ignores (
            legacy_schedule_id INTEGER PRIMARY KEY,
            ignored_by TEXT,
            ignored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reason TEXT
        )
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit schedule duplicate/migration issues. Default is report-only.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true", help="Apply safe cleanup for exact duplicate scheduled_shifts and migrated legacy rows.")
    args = parser.parse_args()

    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        exact_dupes = rows(
            conn,
            """
            SELECT employee_id, shift_date, start_time, end_time, COUNT(*) AS c, GROUP_CONCAT(id) AS ids
            FROM scheduled_shifts
            GROUP BY employee_id, shift_date, start_time, end_time
            HAVING COUNT(*) > 1
            ORDER BY shift_date, employee_id, start_time
            """,
        ) if table_exists(conn, "scheduled_shifts") else []
        legacy_dupes = rows(
            conn,
            """
            SELECT legacy_schedule_id, COUNT(*) AS c, GROUP_CONCAT(id) AS ids
            FROM scheduled_shifts
            WHERE legacy_schedule_id IS NOT NULL
            GROUP BY legacy_schedule_id
            HAVING COUNT(*) > 1
            ORDER BY legacy_schedule_id
            """,
        ) if table_exists(conn, "scheduled_shifts") else []

        print(f"exact_duplicate_groups={len(exact_dupes)}")
        for row in exact_dupes:
            print(f"  exact employee={row['employee_id']} date={row['shift_date']} {row['start_time']}-{row['end_time']} ids={row['ids']}")
        print(f"legacy_duplicate_groups={len(legacy_dupes)}")
        for row in legacy_dupes:
            print(f"  legacy_id={row['legacy_schedule_id']} ids={row['ids']}")

        if not args.apply:
            print("report_only=true")
            return 0

        ensure_ignore_table(conn)
        deleted = 0
        for row in exact_dupes:
            ids = [int(x) for x in str(row["ids"]).split(",") if x]
            keep = max(ids)
            for old_id in ids:
                if old_id != keep:
                    conn.execute("DELETE FROM scheduled_shifts WHERE id=?", (old_id,))
                    deleted += 1
        for row in legacy_dupes:
            ids = [int(x) for x in str(row["ids"]).split(",") if x]
            keep = max(ids)
            for old_id in ids:
                if old_id != keep:
                    conn.execute("DELETE FROM scheduled_shifts WHERE id=?", (old_id,))
                    deleted += 1
        hidden = 0
        if table_exists(conn, "schedules"):
            migrated_legacy_ids = rows(conn, "SELECT DISTINCT legacy_schedule_id FROM scheduled_shifts WHERE legacy_schedule_id IS NOT NULL")
            for item in migrated_legacy_ids:
                legacy_id = item["legacy_schedule_id"]
                if legacy_id is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO legacy_schedule_ignores(legacy_schedule_id, ignored_by, reason) VALUES (?, 'cleanup-script', 'Migrated to scheduled_shifts')",
                        (int(legacy_id),),
                    )
                    hidden += int(conn.total_changes > 0)
        conn.commit()
        print(f"applied=true deleted_scheduled_shifts={deleted} migrated_legacy_hidden_attempts={hidden}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
