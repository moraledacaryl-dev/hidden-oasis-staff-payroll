from __future__ import annotations

from typing import Any

from core.db import fetchall


def ensure_adjustment_event_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_adjustment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL,
            payroll_item_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            adjustment_kind TEXT NOT NULL,
            old_centavos INTEGER NOT NULL,
            new_centavos INTEGER NOT NULL,
            cash_advance_id INTEGER,
            reason TEXT NOT NULL,
            actor_id INTEGER,
            actor_name TEXT NOT NULL,
            request_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_payroll_adjustment_events_run ON payroll_adjustment_events(payroll_run_id,id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_payroll_adjustment_events_item ON payroll_adjustment_events(payroll_item_id,id)"
    )


def append_adjustment_event(
    conn: Any,
    *,
    payroll_run_id: int,
    payroll_item_id: int,
    employee_id: int,
    adjustment_kind: str,
    old_centavos: int,
    new_centavos: int,
    cash_advance_id: int | None,
    reason: str,
    actor_id: int | None,
    actor_name: str,
    request_id: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO payroll_adjustment_events(
            payroll_run_id,payroll_item_id,employee_id,adjustment_kind,
            old_centavos,new_centavos,cash_advance_id,reason,
            actor_id,actor_name,request_id,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payroll_run_id,
            payroll_item_id,
            employee_id,
            adjustment_kind,
            old_centavos,
            new_centavos,
            cash_advance_id,
            reason,
            actor_id,
            actor_name,
            request_id,
            created_at,
        ),
    )


def list_adjustment_events(conn: Any, run_id: int) -> list[dict[str, Any]]:
    return fetchall(
        conn,
        """
        SELECT pae.*, e.full_name AS employee_name
        FROM payroll_adjustment_events pae
        LEFT JOIN employees e ON e.id=pae.employee_id
        WHERE pae.payroll_run_id=?
        ORDER BY pae.created_at ASC, pae.id ASC
        """,
        (run_id,),
    )
