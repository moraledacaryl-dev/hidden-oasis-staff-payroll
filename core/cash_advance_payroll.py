from __future__ import annotations

import sqlite3
from typing import Any

from api.cash_advance_service import ensure_schema, now_iso, recalculate_balance
from core.db import fetchall, fetchone


def apply_payroll_cash_advance_repayments(conn: sqlite3.Connection, run_id: int, actor: str | None = None, reference: str | None = None) -> None:
    """Record cash-advance repayments from a paid payroll run.

    Payroll items already store the computed cash_advance_deduction. This function
    allocates each employee's deduction against that employee's outstanding cash
    advances and writes rows to the current cash_advance_repayments schema.
    """
    ensure_schema(conn)
    run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
    if not run:
        return

    items = fetchall(
        conn,
        "SELECT * FROM payroll_items WHERE payroll_run_id=? AND COALESCE(cash_advance_deduction,0) > 0",
        (run_id,),
    )
    for item in items:
        remaining = round(float(item.get("cash_advance_deduction") or 0), 2)
        if remaining <= 0:
            continue
        advances = fetchall(
            conn,
            """
            SELECT * FROM cash_advances
            WHERE employee_id=?
              AND COALESCE(remaining_balance, outstanding_balance, amount, 0) > 0
              AND COALESCE(status,'') NOT IN ('Cancelled','Fully Paid')
              AND lower(COALESCE(repayment_method,'Payroll deduction')) LIKE '%payroll%'
            ORDER BY date(COALESCE(advance_date, request_date)), id
            """,
            (item["employee_id"],),
        )
        for advance in advances:
            if remaining <= 0:
                break
            already = fetchone(
                conn,
                """
                SELECT id FROM cash_advance_repayments
                WHERE cash_advance_id=? AND payroll_run_id=? AND COALESCE(active,1)=1
                """,
                (advance["id"], run_id),
            )
            if already:
                continue
            current = recalculate_balance(conn, int(advance["id"]))
            balance = round(float(current.get("balance") or 0), 2)
            if balance <= 0:
                continue
            amount = round(min(remaining, balance), 2)
            stamp = now_iso()
            conn.execute(
                """
                INSERT INTO cash_advance_repayments(
                    cash_advance_id, employee_id, repayment_date, amount, source,
                    payment_method, payroll_run_id, payroll_item_id, reference,
                    notes, active, created_by, created_at, updated_by, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)
                """,
                (
                    advance["id"],
                    item["employee_id"],
                    run.get("payout_date") or now_iso()[:10],
                    amount,
                    "Payroll",
                    "Payroll deduction",
                    run_id,
                    item.get("id"),
                    reference,
                    f"Auto-applied from payroll run {run_id}",
                    actor,
                    stamp,
                    actor,
                    stamp,
                ),
            )
            recalculate_balance(conn, int(advance["id"]))
            remaining = round(remaining - amount, 2)


def reverse_payroll_cash_advance_repayments(conn: sqlite3.Connection, run_id: int, actor: str | None = None, reason: str | None = None) -> None:
    ensure_schema(conn)
    stamp = now_iso()
    rows = fetchall(conn, "SELECT * FROM cash_advance_repayments WHERE payroll_run_id=? AND COALESCE(active,1)=1", (run_id,))
    for row in rows:
        conn.execute(
            """
            UPDATE cash_advance_repayments
            SET active=0, reversed_by=?, reversed_at=?, reversal_reason=?, updated_by=?, updated_at=?
            WHERE id=?
            """,
            (actor, stamp, reason or f"Payroll run {run_id} reopened/reversed", actor, stamp, row["id"]),
        )
        recalculate_balance(conn, int(row["cash_advance_id"]))
