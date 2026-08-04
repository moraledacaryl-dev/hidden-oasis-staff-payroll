#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    try:
        server = importlib.import_module("api.server")
        entrypoint_ok = getattr(server, "app", None) is not None
    except Exception as exc:
        entrypoint_ok = False
        print(f"     {exc}")
    failures += print_status(entrypoint_ok, "canonical API entrypoint api.server:app")
    if not db.exists():
        return failures

    conn = sqlite3.connect(db)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        failures += print_status(bool(integrity and str(integrity[0]).lower() == "ok"), "sqlite integrity")
        for table in REQUIRED:
            failures += print_status(table_exists(conn, table), f"table {table}")

        exact_duplicate_groups = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
              SELECT
                employee_id, shift_date, start_time, end_time,
                position, department, break_minutes, status,
                COALESCE(notes, ''), COALESCE(legacy_schedule_id, -1), source,
                COALESCE(review_status, ''), COALESCE(review_reason, ''),
                COALESCE(reviewed_by, ''), COALESCE(reviewed_at, ''),
                approved_exception,
                COUNT(*) AS c
              FROM scheduled_shifts
              GROUP BY
                employee_id, shift_date, start_time, end_time,
                position, department, break_minutes, status,
                COALESCE(notes, ''), COALESCE(legacy_schedule_id, -1), source,
                COALESCE(review_status, ''), COALESCE(review_reason, ''),
                COALESCE(reviewed_by, ''), COALESCE(reviewed_at, ''),
                approved_exception
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        failures += print_status(int(exact_duplicate_groups or 0) == 0, "no exact schedule duplicates")

        same_time_groups = conn.execute(
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
        print(f"INFO same-time schedule groups requiring review: {int(same_time_groups or 0)}")
    finally:
        conn.close()

    compile_cmd = [
        sys.executable,
        "-m",
        "py_compile",
        "api/server.py",
        "api/employees.py",
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
