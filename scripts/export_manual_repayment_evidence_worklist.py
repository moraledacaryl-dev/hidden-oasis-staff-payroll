#!/usr/bin/env python3
"""Export a private, read-only Staff manual-repayment evidence review worklist.

This exports Staff's recorded state and blank human-review columns, not proof
that cash reached the business or Accounting posted a corresponding journal.
It never creates outbox events, adjusts employee balances, or edits either DB.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path
import sqlite3

HEADER = (
    "staff_repayment_id",
    "staff_cash_advance_id",
    "staff_repayment_date",
    "staff_amount_php",
    "staff_recorded_method",
    "staff_receipt_reference_present",
    "staff_accounting_handoff",
    "original_receipt_verified",
    "cashbook_or_deposit_verified",
    "actual_receiving_method_verified",
    "actual_receiving_account_verified",
    "accounting_intake_or_journal_verified",
    "payroll_deduction_conflict_checked",
    "possible_duplicate_cash_receipt_checked",
    "reconciliation_decision",
    "reviewer",
    "review_date",
    "private_evidence_location",
    "review_notes",
)

REVIEW_COLUMNS = (
    "original_receipt_verified",
    "cashbook_or_deposit_verified",
    "actual_receiving_method_verified",
    "actual_receiving_account_verified",
    "accounting_intake_or_journal_verified",
    "payroll_deduction_conflict_checked",
    "possible_duplicate_cash_receipt_checked",
)
DOCUMENTED_METHODS = {
    "cash", "gcash", "bank", "bank_transfer", "bank_deposit",
    "cheque", "check", "maya",
}


def php_cents(value: object) -> int:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Nonfinite historical repayment amount")
    return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalize_method(value: object) -> str:
    return "_".join(str(value or "").lower().strip().replace("-", " ").replace("_", " ").split())


def build_worklist(conn: sqlite3.Connection, *, include_all: bool = False) -> tuple[list[dict], dict]:
    """Read Staff under the caller's transaction snapshot; no writes."""
    conn.row_factory = sqlite3.Row
    required = {
        "cash_advance_repayments": {
            "id", "cash_advance_id", "amount", "repayment_date", "source",
            "active", "payment_method", "method", "reference",
        },
        "integration_outbox": {
            "id", "status", "destination", "event_type", "external_source",
            "external_id",
        },
    }
    for table, columns in required.items():
        present = {str(column[1]) for column in conn.execute(f"PRAGMA table_info({table})")}
        if missing := columns - present:
            raise RuntimeError(f"Staff table {table} missing columns: {sorted(missing)}")

    records = conn.execute("""
        SELECT r.id, r.cash_advance_id, r.repayment_date, r.amount,
               COALESCE(NULLIF(TRIM(r.payment_method),''),
                        NULLIF(TRIM(r.method),''),'') AS method,
               CASE WHEN NULLIF(TRIM(r.reference),'') IS NULL THEN 0 ELSE 1
               END AS has_reference,
               o.status AS outbox_status, o.id AS outbox_id
        FROM cash_advance_repayments r
        LEFT JOIN integration_outbox o ON o.id = (
            SELECT MAX(ev.id) FROM integration_outbox ev
            WHERE ev.destination='accounting'
              AND ev.external_source='hidden_oasis_staff_payroll'
              AND ev.event_type='cash_advance.repaid'
              AND ev.external_id='cash-advance-repayment:' || r.id
        )
        WHERE LOWER(TRIM(COALESCE(r.source,'')))='manual'
          AND COALESCE(r.active,1)=1
        ORDER BY r.repayment_date, r.id
    """).fetchall()

    worklist = []
    amount_cents = 0
    exception_count = 0
    for record in records:
        raw_status = str(record["outbox_status"] or "").strip()
        if record["outbox_id"] is None:
            handoff = "missing_staff_outbox"
        elif raw_status == "Completed":
            handoff = "delivered_posting_unverified"
        elif raw_status == "Pending":
            handoff = "pending_delivery"
        else:
            handoff = "delivery_requires_review"

        method = str(record["method"])
        method_unverified = _normalize_method(method) not in DOCUMENTED_METHODS
        needs_review = handoff != "delivered_posting_unverified" or method_unverified
        if needs_review:
            exception_count += 1
        if not include_all and not needs_review:
            continue

        cents = php_cents(record["amount"])
        amount_cents += cents
        item = {
            "staff_repayment_id": int(record["id"]),
            "staff_cash_advance_id": int(record["cash_advance_id"]),
            "staff_repayment_date": str(record["repayment_date"]),
            "staff_amount_php": f"{cents // 100}.{cents % 100:02d}",
            "staff_recorded_method": method,
            "staff_receipt_reference_present": "YES" if record["has_reference"] else "NO",
            "staff_accounting_handoff": handoff,
            **{column: "NOT_REVIEWED" for column in REVIEW_COLUMNS},
            "reconciliation_decision": "PENDING_EVIDENCE",
            "reviewer": "",
            "review_date": "",
            "private_evidence_location": "",
            "review_notes": "",
        }
        worklist.append(item)

    return worklist, {
        "database_read_only": True,
        "scope": "all active manual repayments" if include_all else "Staff delivery or receipt-method exceptions",
        "active_manual_repayment_count": len(records),
        "exception_count": exception_count,
        "exported_case_count": len(worklist),
        "exported_amount_php": amount_cents / 100,
        "financial_postings_or_replays_performed": 0,
        "cash_custody_verified_by_this_export": False,
    }


def _safe_spreadsheet_cell(value: object) -> object:
    """Prevent spreadsheet formula interpretation of untrusted Staff text."""
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\\t", "\\r", "\\n")):
        return "'" + value
    return value


def export_private_csv(path: Path, rows: list[dict]) -> None:
    """Create a new private file exclusively; refuse overwrite and symlinks."""
    if not path.is_absolute() or not path.parent.is_dir():
        raise ValueError("--output must be an absolute path under an existing directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=HEADER, extrasaction="raise")
            writer.writeheader()
            for item in rows:
                writer.writerow({key: _safe_spreadsheet_cell(value) for key, value in item.items()})
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path,
        default=Path(os.environ["STAFF_PAYROLL_DB_PATH"])
        if os.getenv("STAFF_PAYROLL_DB_PATH") else None,
    )
    parser.add_argument("--output", required=True, type=Path,
                        help="New private CSV file; existing files will not be overwritten")
    parser.add_argument("--all-manual", action="store_true",
                        help="Include even delivered/manual repayments; delivery is not proof of posting")
    args = parser.parse_args()
    if args.db is None or not args.db.is_absolute() or not args.db.is_file():
        parser.error("--db must reference an existing absolute Staff SQLite DB")
    if not args.output.is_absolute() or not args.output.parent.is_dir():
        parser.error("--output must be an absolute path in an existing directory")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        items, summary = build_worklist(conn, include_all=args.all_manual)
    export_private_csv(args.output, items)
    print(json.dumps({**summary, "output_file": str(args.output),
                      "output_permissions": "0600"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
