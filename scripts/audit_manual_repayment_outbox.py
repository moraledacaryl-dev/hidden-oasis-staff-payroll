#!/usr/bin/env python3
"""Read-only audit of manual cash-advance receipts versus Staff Accounting outbox.

A missing Staff outbox event does NOT prove a missing Accounting receipt:
historical payments may already have been entered directly in Accounting.
Do not re-enqueue or post money based solely on this report.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def php_cents(amount: object) -> int:
    return int(
        (Decimal(str(amount or "0")) * Decimal(100))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def audit_manual_repayment_outbox(
    conn: sqlite3.Connection, *, sample_limit: int = 100
) -> dict:
    """Report historical active manual repayments without matching outbox events.

    No mutations are made. Staff outbox Completed proves only delivery, not
    Accounting approval or final financial posting.
    """
    if sample_limit < 0:
        raise ValueError("sample_limit must be nonnegative")
    conn.row_factory = sqlite3.Row
    required = {
        "cash_advance_repayments": {
            "id", "cash_advance_id", "amount", "source", "active",
            "repayment_date", "payment_method", "method", "reference",
        },
        "integration_outbox": {
            "id", "destination", "event_type", "external_source", "external_id", "status",
        },
    }
    for table, columns in required.items():
        existing = {
            str(item[1]) for item in conn.execute(f"PRAGMA table_info({table})")
        }
        missing = columns - existing
        if missing:
            raise RuntimeError(
                f"Missing columns in {table}: {', '.join(sorted(missing))}"
            )

    rows = conn.execute(
        """
        SELECT
            repayment.id AS repayment_id,
            repayment.cash_advance_id,
            repayment.repayment_date,
            repayment.amount,
            COALESCE(NULLIF(TRIM(repayment.payment_method),''),
                     NULLIF(TRIM(repayment.method),''), '') AS payment_method,
            COALESCE(TRIM(repayment.reference), '') AS receipt_reference,
            outbox.id AS outbox_id,
            outbox.status AS outbox_status
        FROM cash_advance_repayments AS repayment
        LEFT JOIN integration_outbox AS outbox
          ON outbox.destination='accounting'
         AND outbox.external_source='hidden_oasis_staff_payroll'
         AND outbox.event_type='cash_advance.repaid'
         AND outbox.external_id='cash-advance-repayment:' || repayment.id
        WHERE LOWER(TRIM(COALESCE(repayment.source,'')))='manual'
          AND COALESCE(repayment.active,1)=1
        ORDER BY repayment.id
        """
    ).fetchall()

    categories: Counter[str] = Counter()
    sums_cents: Counter[str] = Counter()
    details: list[dict] = []
    duplicate_groups: dict[tuple, list[int]] = {}
    for row in rows:
        data = dict(row)
        status = str(data["outbox_status"] or "").strip()
        if data["outbox_id"] is None:
            category = "missing_staff_outbox"
        elif status == "Completed":
            category = "delivered_not_necessarily_posted"
        else:
            category = "outbox_not_completed"
        categories[category] += 1
        sums_cents[category] += php_cents(data["amount"])
        detail = {
            "repayment_id": int(data["repayment_id"]),
            "cash_advance_id": int(data["cash_advance_id"]),
            "repayment_date": str(data["repayment_date"] or ""),
            "amount_php": php_cents(data["amount"]) / 100,
            "payment_method": data["payment_method"],
            "outbox_id": data["outbox_id"],
            "outbox_status": status or None,
            "classification": category,
        }
        # Report a reference-presence flag, not potentially sensitive receipt
        # or bank transaction reference values.
        detail["has_receipt_reference"] = bool(data["receipt_reference"])
        details.append(detail)

        # Repeat exact advance/day/amount/method/reference is a *candidate*
        # duplicate only; two legitimate installments can share these values.
        fingerprint = (
            data["cash_advance_id"],
            data["repayment_date"],
            php_cents(data["amount"]),
            str(data["payment_method"] or "").strip().lower(),
            str(data["receipt_reference"] or "").strip().lower(),
        )
        duplicate_groups.setdefault(fingerprint, []).append(int(data["repayment_id"]))

    needs_review = [
        d for d in details if d["classification"] != "delivered_not_necessarily_posted"
    ]
    duplicates = [
        {"repayment_ids": ids, "count": len(ids)}
        for ids in duplicate_groups.values()
        if len(ids) > 1
    ]
    return {
        "read_only": True,
        "scope": "active manual cash-advance repayments in Staff DB",
        "manual_repayment_count": len(details),
        "manual_repayment_amount_php": sum(php_cents(d["amount_php"]) for d in details) / 100,
        "missing_staff_outbox_count": categories["missing_staff_outbox"],
        "missing_staff_outbox_amount_php": sums_cents["missing_staff_outbox"] / 100,
        "outbox_not_completed_count": categories["outbox_not_completed"],
        "outbox_not_completed_amount_php": sums_cents["outbox_not_completed"] / 100,
        "delivered_not_necessarily_posted_count": categories["delivered_not_necessarily_posted"],
        "review_candidate_count": len(needs_review),
        "review_candidate_sample": needs_review[:sample_limit],
        "review_candidate_sample_truncated": len(needs_review) > sample_limit,
        "possible_duplicate_groups_count": len(duplicates),
        "possible_duplicate_groups_sample": duplicates[:sample_limit],
        "instructions": (
            "A missing Staff outbox event does not prove a missing Accounting "
            "transaction. Compare receipt IDs, employee advance ledgers, "
            "Accounting review queue and cash/bank/GCash statements before "
            "any manual adjustment or controlled replay. A Completed outbox "
            "event establishes delivery only, not that Accounting accepted or "
            "posted the payment. Duplicate candidates may be legitimate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ["STAFF_PAYROLL_DB_PATH"])
        if os.getenv("STAFF_PAYROLL_DB_PATH") else None,
        help="Existing absolute path to the Staff Payroll SQLite database",
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Maximum detailed repayment/duplicate examples (default 100; 0 for summary only)",
    )
    args = parser.parse_args()
    if not args.db or not args.db.is_absolute() or not args.db.is_file():
        parser.error("Provide an existing absolute SQLite database path")
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        report = audit_manual_repayment_outbox(conn, sample_limit=args.limit)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
