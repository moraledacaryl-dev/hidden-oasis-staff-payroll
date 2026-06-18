from __future__ import annotations

import json
from typing import Any

from core.db import fetchone


def ensure_schedule_change_log_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_change_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            change_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            employee_id INTEGER,
            work_date TEXT,
            payroll_run_id INTEGER,
            before_json TEXT,
            after_json TEXT,
            changed_by TEXT,
            changed_at TEXT NOT NULL,
            undone_at TEXT,
            undone_by TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_change_logs_work_date ON schedule_change_logs(work_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_change_logs_payroll_run ON schedule_change_logs(payroll_run_id)")


def latest_saved_run_for_day(conn, work_date: str | None) -> dict[str, Any] | None:
    if not work_date:
        return None
    return fetchone(
        conn,
        """
        SELECT id, status, period_start, period_end, created_at, paid_at
        FROM payroll_runs
        WHERE date(?) BETWEEN date(period_start) AND date(period_end)
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (work_date,),
    )


def dump_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def log_schedule_change(
    conn,
    *,
    change_type: str,
    entity_type: str,
    entity_id: int | None,
    employee_id: int | None,
    work_date: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    changed_by: str | None,
) -> int:
    ensure_schedule_change_log_schema(conn)
    run = latest_saved_run_for_day(conn, work_date)
    cur = conn.execute(
        """
        INSERT INTO schedule_change_logs(
            change_type, entity_type, entity_id, employee_id, work_date, payroll_run_id,
            before_json, after_json, changed_by, changed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """,
        (
            change_type,
            entity_type,
            entity_id,
            employee_id,
            work_date,
            int(run["id"]) if run else None,
            dump_json(before),
            dump_json(after),
            changed_by,
        ),
    )
    return int(cur.lastrowid)
