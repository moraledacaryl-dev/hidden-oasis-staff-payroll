#!/usr/bin/env python3
"""Read-only report of possibly lost advance repayments from paid adjustments.

Use the same production database path as the Staff service. No record is ever
updated. Findings require human reconciliation against payslips, remittance
history and any subsequent corrections before attempting adjustments.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path


def audit_paid_adjustment_reversals(conn: sqlite3.Connection) -> dict:
    """Find repayments reversed specifically by a finalized adjustment revision."""
    conn.row_factory = sqlite3.Row
    required = {
        "payroll_runs": {"id", "status", "paid_at", "revision_of_run_id", "revision_treatment"},
        "cash_advance_repayments": {
            "id", "cash_advance_id", "payroll_run_id", "amount", "active",
            "reversal_reason", "reversed_at",
        },
    }
    for table, columns in required.items():
        existing = {str(item[1]) for item in conn.execute(f"PRAGMA table_info({table})")}
        missing = columns - existing
        if missing:
            raise RuntimeError(f"Missing columns in {table}: {', '.join(sorted(missing))}")
    rows = conn.execute(
        """
        SELECT
            revision.id AS revision_run_id,
            parent.id AS original_paid_run_id,
            repayment.id AS repayment_id,
            repayment.cash_advance_id,
            ROUND(repayment.amount, 2) AS amount,
            repayment.reversed_at,
            repayment.reversal_reason
        FROM payroll_runs AS revision
        JOIN payroll_runs AS parent ON parent.id = revision.revision_of_run_id
        JOIN cash_advance_repayments AS repayment
          ON repayment.payroll_run_id = parent.id
        WHERE LOWER(COALESCE(revision.revision_treatment,'')) = 'adjust_paid'
          AND (
            LOWER(COALESCE(revision.status,'')) IN ('paid','locked')
            OR revision.paid_at IS NOT NULL
          )
          AND (
            LOWER(COALESCE(parent.status,'')) IN ('paid','locked')
            OR parent.paid_at IS NOT NULL
          )
          AND COALESCE(repayment.active,1) = 0
          AND repayment.reversal_reason = (
            'Superseded by paid payroll revision #' || revision.id
          )
        ORDER BY revision.id, repayment.id
        """
    ).fetchall()
    findings = [dict(row) for row in rows]
    cents = sum(round(float(row["amount"]) * 100) for row in findings)
    return {
        "read_only": True,
        "finding_count": len(findings),
        "potentially_reversed_amount_php": cents / 100,
        "findings": findings,
        "instruction": (
            "Review each flagged repayment against the original paid payslip, "
            "cash-advance ledger and later corrections before changing any balances."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path,
        default=Path(os.environ["STAFF_PAYROLL_DB_PATH"]) if os.getenv("STAFF_PAYROLL_DB_PATH") else None,
        help="Absolute path to the Staff & Payroll SQLite database",
    )
    args = parser.parse_args()
    if args.db is None or not args.db.is_absolute() or not args.db.is_file():
        parser.error("Provide an existing absolute database path with --db or STAFF_PAYROLL_DB_PATH")
    db = args.db.resolve()
    uri = db.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        print(json.dumps(audit_paid_adjustment_reversals(conn), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
