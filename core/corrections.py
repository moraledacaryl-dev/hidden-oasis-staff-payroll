from __future__ import annotations

from typing import Any
import sqlite3

from .db import fetchall, fetchone, now_iso


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    row = fetchone(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not row or not int(row.get("c") or 0):
        return set()
    return {str(info[1]) for info in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_payroll_corrections_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            adjustment_type TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            apply_to_next_run INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Recorded',
            applied_to_run_id INTEGER,
            applied_at TEXT,
            voided_by TEXT,
            void_reason TEXT,
            voided_at TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column(conn, "payroll_corrections", "status", "TEXT NOT NULL DEFAULT 'Recorded'")
    ensure_column(conn, "payroll_corrections", "applied_to_run_id", "INTEGER")
    ensure_column(conn, "payroll_corrections", "applied_at", "TEXT")
    ensure_column(conn, "payroll_corrections", "voided_by", "TEXT")
    ensure_column(conn, "payroll_corrections", "void_reason", "TEXT")
    ensure_column(conn, "payroll_corrections", "voided_at", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payroll_corrections_run ON payroll_corrections(payroll_run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payroll_corrections_employee ON payroll_corrections(employee_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payroll_corrections_status ON payroll_corrections(status, apply_to_next_run)")


def eligible_corrections(conn: sqlite3.Connection, employee_id: int, period_start: str) -> list[dict[str, Any]]:
    ensure_payroll_corrections_schema(conn)
    return fetchall(
        conn,
        """
        SELECT pc.*, pr.period_start AS source_period_start, pr.period_end AS source_period_end
        FROM payroll_corrections pc
        JOIN payroll_runs pr ON pr.id = pc.payroll_run_id
        WHERE pc.employee_id=?
          AND pc.apply_to_next_run=1
          AND pc.status='Recorded'
          AND pc.adjustment_type IN ('Earning', 'Deduction')
          AND date(pr.period_end) < date(?)
        ORDER BY pr.period_end, pc.id
        """,
        (employee_id, period_start),
    )


def mark_eligible_corrections_applied(conn: sqlite3.Connection, run_id: int, period_start: str) -> None:
    ensure_payroll_corrections_schema(conn)
    conn.execute(
        """
        UPDATE payroll_corrections
        SET status='Applied', applied_to_run_id=?, applied_at=?
        WHERE id IN (
            SELECT pc.id
            FROM payroll_corrections pc
            JOIN payroll_runs pr ON pr.id = pc.payroll_run_id
            WHERE pc.apply_to_next_run=1
              AND pc.status='Recorded'
              AND pc.adjustment_type IN ('Earning', 'Deduction')
              AND date(pr.period_end) < date(?)
        )
        """,
        (run_id, now_iso(), period_start),
    )
