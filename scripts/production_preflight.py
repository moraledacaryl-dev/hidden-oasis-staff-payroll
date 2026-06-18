#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

DB = Path(os.getenv("STAFF_PAYROLL_DB_PATH", "data/staff_payroll.sqlite"))
REQUIRED = [
    "app_users",
    "employees",
    "payroll_runs",
    "payroll_items",
    "scheduled_shifts",
    "time_logs",
    "schedule_change_logs",
    "legacy_schedule_ignores",
    "payroll_revision_change_links",
]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def print_status(ok: bool, label: str) -> int:
    print(("OK   " if ok else "FAIL ") + label)
    return 0 if ok else 1


def main() -> int:
    failures = 0
    db = DB.expanduser().resolve()
    failures += print_status(db.exists(), f"database exists: {db}")
    failures += print_status(bool(os.getenv("STAFF_PAYROLL_API_KEY")), "api key configured")
    failures += print_status(bool(os.getenv("STAFF_PAYROLL_SESSION_SECRET")), "session secret configured")
    if not db.exists():
        return failures

    conn = sqlite3.connect(db)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        failures += print_status(bool(integrity and str(integrity[0]).lower() == "ok"), "sqlite integrity")
        for table in REQUIRED:
            failures += print_status(table_exists(conn, table), f"table {table}")
        duplicate_groups = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
              SELECT employee_id, shift_date, start_time, end_time, COUNT(*) AS c
              FROM scheduled_shifts
              GROUP BY employee_id, shift_date, start_time, end_time
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        failures += print_status(int(duplicate_groups or 0) == 0, "no exact schedule duplicates")
    finally:
        conn.close()

    compile_cmd = [
        sys.executable,
        "-m",
        "py_compile",
        "api/server_review.py",
        "api/schedules.py",
        "api/payroll_revision_controls.py",
        "api/production_health.py",
    ]
    result = subprocess.run(compile_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    failures += print_status(result.returncode == 0, "python compile")
    if result.returncode != 0:
        print(result.stdout)

    if failures:
        print(f"Production preflight failed: {failures}")
        return 1
    print("Production preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
