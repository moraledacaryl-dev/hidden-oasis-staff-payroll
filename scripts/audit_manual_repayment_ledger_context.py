#!/usr/bin/env python3
"""Read-only ledger context for historical manual repayments missing Accounting outbox events.

A recorded Staff repayment may reduce an employee's cash-advance balance without
establishing that cash reached the business. No transactions are posted, reversed,
or replayed by this audit. Names, notes, and receipt references are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


PAID_STATES = {"Paid", "Locked", "Released"}


def centavos(value: object) -> int:
    number = Decimal(str(value if value is not None else 0))
    if not number.is_finite():
        raise ValueError("Nonfinite amount found in Staff financial ledger")
    return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def audit_ledger(conn: sqlite3.Connection, *, sample_limit: int = 30) -> dict:
    if sample_limit < 0:
        raise ValueError("sample_limit must not be negative")
    conn.row_factory = sqlite3.Row
    required = {
        "cash_advances": {
            "id", "amount", "ledger_opening_balance", "remaining_balance",
            "outstanding_balance", "status",
        },
        "cash_advance_repayments": {
            "id", "cash_advance_id", "source", "amount", "repayment_date",
            "active", "payroll_run_id", "payment_method", "method", "reference",
        },
        "payroll_runs": {"id", "status"},
        "integration_outbox": {
            "destination", "external_source", "event_type", "external_id",
        },
    }
    for table, needed in required.items():
        missing = needed - _columns(conn, table)
        if missing:
            raise RuntimeError(f"Staff {table} missing columns: {sorted(missing)}")

    targets = conn.execute("""
        SELECT r.id, r.cash_advance_id, r.repayment_date, r.amount,
               COALESCE(NULLIF(TRIM(r.payment_method), ''),
                        NULLIF(TRIM(r.method), ''), '') AS method,
               CASE WHEN NULLIF(TRIM(r.reference), '') IS NULL THEN 0 ELSE 1
               END AS has_reference
        FROM cash_advance_repayments r
        WHERE LOWER(TRIM(COALESCE(r.source,'')))='manual'
          AND COALESCE(r.active,1)=1
          AND NOT EXISTS (
              SELECT 1 FROM integration_outbox o
              WHERE o.destination='accounting'
                AND o.external_source='hidden_oasis_staff_payroll'
                AND o.event_type='cash_advance.repaid'
                AND o.external_id='cash-advance-repayment:' || r.id
          )
        ORDER BY r.id
    """).fetchall()

    cases = []
    cross_advance_dates: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)
    totals = Counter()
    for row in targets:
        advance = conn.execute("""
            SELECT id, amount, ledger_opening_balance, remaining_balance,
                   outstanding_balance, status
            FROM cash_advances WHERE id=?
        """, (row["cash_advance_id"],)).fetchone()
        if advance is None:
            raise RuntimeError(f"Repayment {row['id']} has no cash-advance parent")
        # Mirror cash_advance_service.calculate_balance's opening choice.
        opening_source = "ledger_opening_balance"
        opening_value = advance["ledger_opening_balance"]
        if opening_value is None:
            opening_source = "legacy_balance_fallback"
            opening_value = (
                advance["remaining_balance"] or advance["outstanding_balance"]
                or advance["amount"] or 0
            )
        opening_cents = centavos(opening_value)
        repayment_rows = conn.execute("""
            SELECT r.id, r.amount, r.source, r.active, r.payroll_run_id,
                   pr.status AS payroll_status
            FROM cash_advance_repayments r
            LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
            WHERE r.cash_advance_id=?
            ORDER BY r.id
        """, (row["cash_advance_id"],)).fetchall()
        active_manual = 0
        confirmed_payroll = 0
        unconfirmed_payroll = 0
        reversed_total = 0
        unexpected_sources = []
        same_advance_amount = []
        for p in repayment_rows:
            amount = centavos(p["amount"])
            if not int(p["active"] if p["active"] is not None else 1):
                reversed_total += amount
                continue
            if str(p["source"] or "") == "Manual":
                active_manual += amount
                if p["id"] != row["id"] and amount == centavos(row["amount"]):
                    same_advance_amount.append(int(p["id"]))
            elif str(p["payroll_status"] or "") in PAID_STATES:
                confirmed_payroll += amount
            else:
                unconfirmed_payroll += amount
                if str(p["source"] or "") not in {"Payroll", "Manual"}:
                    unexpected_sources.append(int(p["id"]))
        confirmed_total = active_manual + confirmed_payroll
        calculated_balance = max(0, opening_cents - confirmed_total)
        stored_remaining = centavos(advance["remaining_balance"])
        stored_outstanding = centavos(advance["outstanding_balance"])
        issues = []
        if opening_cents < 0 or centavos(advance["amount"]) < 0:
            issues.append("negative_advance_or_opening")
        if confirmed_total > opening_cents:
            issues.append("confirmed_repayments_exceed_ledger_opening")
        if stored_remaining != calculated_balance:
            issues.append("stored_remaining_differs_from_calculated")
        if stored_outstanding != calculated_balance:
            issues.append("stored_outstanding_differs_from_calculated")
        if unexpected_sources:
            issues.append("unusual_repayment_source")
        if str(row["method"]).strip().lower() not in {
            "cash", "gcash", "bank", "bank transfer", "bank_transfer",
            "bank deposit", "bank_deposit", "check", "cheque", "maya",
        }:
            issues.append("payment_method_needs_verification")
        target_amount = centavos(row["amount"])
        cross_advance_dates[(str(row["repayment_date"]), target_amount)].append(
            (int(row["id"]), int(row["cash_advance_id"]))
        )
        totals["amount_cents"] += target_amount
        totals["issues"] += bool(issues)
        cases.append({
            "repayment_id": int(row["id"]),
            "cash_advance_id": int(row["cash_advance_id"]),
            "repayment_date": str(row["repayment_date"]),
            "amount_php": target_amount / 100,
            "payment_method": str(row["method"]),
            "has_reference": bool(row["has_reference"]),
            "advance_amount_php": centavos(advance["amount"]) / 100,
            "advance_status": str(advance["status"]),
            "ledger_opening_source": opening_source,
            "ledger_opening_php": opening_cents / 100,
            "active_manual_repaid_php": active_manual / 100,
            "confirmed_payroll_deductions_php": confirmed_payroll / 100,
            "unconfirmed_payroll_repayments_php": unconfirmed_payroll / 100,
            "inactive_repayment_amount_php": reversed_total / 100,
            "calculated_remaining_php": calculated_balance / 100,
            "stored_remaining_php": stored_remaining / 100,
            "stored_outstanding_php": stored_outstanding / 100,
            "same_advance_equal_amount_repayment_ids": same_advance_amount,
            "review_flags": issues,
            "cash_receipt_independently_verified": False,
        })

    # Same-day, same-amount installments across *different* advances may both
    # be legitimate. Report overlaps without suggesting either is a duplicate.
    overlapping = [
        {
            "repayment_date": day,
            "amount_php": amount_cents / 100,
            "repayment_ids": [rid for rid, _ in refs],
            "cash_advance_ids": sorted({aid for _, aid in refs}),
        }
        for (day, amount_cents), refs in sorted(cross_advance_dates.items())
        if len(refs) > 1 and len({aid for _, aid in refs}) > 1
    ]
    return {
        "read_only": True,
        "scope": "active manual repayments missing Staff Accounting outbox",
        "repayment_count": len(cases),
        "total_repayment_php": totals["amount_cents"] / 100,
        "cases_with_ledger_or_method_review_flags": totals["issues"],
        "shared_date_amount_across_advances_count": len(overlapping),
        "shared_date_amount_across_advances": overlapping[:sample_limit],
        "cases": cases[:sample_limit],
        "sample_truncated": len(cases) > sample_limit,
        "instruction": (
            "Staff balance arithmetic does not establish cash custody. Reconcile "
            "each original receipt, cash-book entry, deposit, Accounting ledger "
            "and payroll deduction. Do not backfill or replay until independently "
            "verified; similar payments across different advances may be legitimate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path,
                        default=Path(os.environ["STAFF_PAYROLL_DB_PATH"])
                        if os.getenv("STAFF_PAYROLL_DB_PATH") else None)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if args.db is None or not args.db.is_absolute() or not args.db.is_file():
        parser.error("--db must refer to an existing absolute Staff SQLite DB")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        report = audit_ledger(db, sample_limit=args.limit)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
