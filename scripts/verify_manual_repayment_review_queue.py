#!/usr/bin/env python3
"""Read-only production parity check: Cash Advances UI handoff queue vs Staff outbox.

This checks Staff source and UI/API projection consistency, NOT evidence of
cash custody, an accepted Accounting intake, or an Accounting journal.
It refuses to repair, enqueue or post anything.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.cash_advance_service import repayment_history
from scripts.audit_manual_repayment_outbox import audit_manual_repayment_outbox


def cents(value: object) -> int:
    amount = Decimal(str(value if value is not None else 0))
    if not amount.is_finite():
        raise ValueError("Nonfinite repayment amount in Staff source ledger")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def verify_review_queue(conn: sqlite3.Connection, *, sample_limit: int = 30) -> dict:
    if sample_limit < 0:
        raise ValueError("sample_limit must be >= 0")
    conn.row_factory = sqlite3.Row
    source = audit_manual_repayment_outbox(conn, sample_limit=0)
    # The same snapshot is used by all queries. Caller should BEGIN a
    # read transaction for production consistency with concurrent writers.
    target_rows = conn.execute("""
        SELECT id, cash_advance_id, amount
        FROM cash_advance_repayments
        WHERE LOWER(TRIM(COALESCE(source,''))) = 'manual'
          AND COALESCE(active,1) = 1
        ORDER BY id
    """).fetchall()

    rows_by_id: dict[int, dict] = {}
    missing_from_projection: list[int] = []
    duplicate_projection: list[int] = []
    for advance_id in sorted({int(row["cash_advance_id"]) for row in target_rows}):
        for item in repayment_history(conn, advance_id):
            if str(item.get("source") or "").strip().lower() != "manual":
                continue
            rid = int(item["id"])
            if rid in rows_by_id:
                duplicate_projection.append(rid)
            rows_by_id[rid] = item

    # Separate comparison with actual durable Staff outbox rows. We do not
    # infer downstream Accounting posting from any Staff event status.
    mismatches: list[dict] = []
    counts: Counter[str] = Counter()
    amounts: Counter[str] = Counter()
    for row in target_rows:
        rid = int(row["id"])
        outboxes = conn.execute("""
            SELECT id, status FROM integration_outbox
            WHERE destination='accounting'
              AND external_source='hidden_oasis_staff_payroll'
              AND event_type='cash_advance.repaid'
              AND external_id=?
            ORDER BY id DESC
        """, (f"cash-advance-repayment:{rid}",)).fetchall()
        if len(outboxes) > 1:
            mismatches.append({"repayment_id": rid, "reason": "duplicate_exact_outbox_identity"})
        if not outboxes:
            expected = "missing_staff_outbox"
        elif outboxes[0]["status"] == "Completed":
            expected = "delivered_posting_unverified"
        elif outboxes[0]["status"] == "Pending":
            expected = "pending_delivery"
        else:
            expected = "delivery_requires_review"
        counts[expected] += 1
        amounts[expected] += cents(row["amount"])

        item = rows_by_id.get(rid)
        if item is None:
            missing_from_projection.append(rid)
            continue
        actual = item.get("accounting_handoff_state")
        if actual != expected:
            mismatches.append({
                "repayment_id": rid,
                "reason": "handoff_state_differs",
                "expected": expected,
                "actual": actual,
            })
        if cents(item["amount"]) != cents(row["amount"]):
            mismatches.append({"repayment_id": rid, "reason": "projection_amount_differs"})

    review_states = {"missing_staff_outbox", "delivery_requires_review"}
    review_count = sum(counts[state] for state in review_states)
    review_cents = sum(amounts[state] for state in review_states)
    projected_total = sum(counts.values())
    summary_matches = (
        source["manual_repayment_count"] == projected_total
        and source["missing_staff_outbox_count"] == counts["missing_staff_outbox"]
        and source["outbox_not_completed_count"] == (
            counts["pending_delivery"] + counts["delivery_requires_review"]
        )
        and source["delivered_not_necessarily_posted_count"] ==
        counts["delivered_posting_unverified"]
        and cents(source["missing_staff_outbox_amount_php"]) ==
        amounts["missing_staff_outbox"]
        and cents(source["outbox_not_completed_amount_php"]) ==
        amounts["pending_delivery"] + amounts["delivery_requires_review"]
    )
    passed = (
        summary_matches
        and not mismatches
        and not missing_from_projection
        and not duplicate_projection
        and len(rows_by_id) == len(target_rows)
    )
    return {
        "read_only": True,
        "passed": passed,
        "scope": "Staff cash-advance manual repayment handoff projection parity",
        "manual_repayment_count": len(target_rows),
        "manual_repayment_amount_php": sum(cents(r["amount"]) for r in target_rows) / 100,
        "ui_handoff_review_count": review_count,
        "ui_handoff_review_amount_php": review_cents / 100,
        "missing_staff_outbox_count": counts["missing_staff_outbox"],
        "pending_delivery_count": counts["pending_delivery"],
        "delivery_requires_review_count": counts["delivery_requires_review"],
        "delivered_posting_unverified_count": counts["delivered_posting_unverified"],
        "source_summary_matches": summary_matches,
        "missing_from_projection_count": len(missing_from_projection),
        "duplicate_projection_count": len(duplicate_projection),
        "mismatch_count": len(mismatches),
        "mismatch_sample": mismatches[:sample_limit],
        "missing_from_projection_sample": missing_from_projection[:sample_limit],
        "duplicate_projection_sample": duplicate_projection[:sample_limit],
        "sample_truncated": any(len(rows) > sample_limit for rows in (
            mismatches, missing_from_projection, duplicate_projection,
        )),
        "accounting_posting_verified": False,
        "cash_custody_verified": False,
        "instruction": (
            "A passing result verifies Staff source/outbox/UI projection consistency "
            "only. Even a Completed Staff delivery does not establish accepted or "
            "posted Accounting intake. Resolve cash receipt evidence separately; "
            "never replay financial events based on this report alone."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path,
        default=Path(os.environ["STAFF_PAYROLL_DB_PATH"])
        if os.getenv("STAFF_PAYROLL_DB_PATH") else None,
    )
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    if args.db is None or not args.db.is_absolute() or not args.db.is_file():
        parser.error("--db must be an existing absolute Staff SQLite database path")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        report = verify_review_queue(conn, sample_limit=args.limit)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
