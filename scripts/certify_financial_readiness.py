#!/usr/bin/env python3
"""Read-only Staff payroll financial certification triage.

This is a local Staff-ledger consistency report, not confirmation that cash
arrived, that Accounting posted any entry, or that an agency received money.
No SQL writes, integrations, backup creation, or settlement actions are made.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_manual_repayment_outbox import audit_manual_repayment_outbox
from scripts.audit_paid_adjustment_reversals import audit_paid_adjustment_reversals

BACKUP_SUFFIXES = (".sqlite", ".sqlite.fernet", ".zip", ".zip.fernet")
REQUIRED = {
    "payroll_runs": {"id", "period_start", "period_end", "status", "paid_at",
                     "revision_of_run_id", "revision_treatment", "superseded_by_run_id"},
    "payroll_items": {"id", "payroll_run_id", "gross_pay", "total_deductions", "net_pay"},
    "cash_advances": {"id"},
    "cash_advance_repayments": {"id", "cash_advance_id", "payroll_run_id", "amount",
                                "active", "reversal_reason", "reversed_at",
                                "source", "repayment_date", "payment_method",
                                "method", "reference"},
    "integration_outbox": {"id", "destination", "event_type", "external_source",
                            "external_id", "status"},
    "statutory_agency_remittances": {
        "id", "program", "contribution_month", "payment_date", "amount", "reference"
    },
    "payroll_statutory_months": {"id", "payroll_run_id", "month_start"},
}


def cents(value: Any) -> int:
    try:
        amount = Decimal(str(value if value is not None else 0))
        if not amount.is_finite():
            raise ValueError("Nonfinite financial amount")
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid financial amount") from exc


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def check_money(conn: sqlite3.Connection, limit: int) -> dict[str, Any]:
    mismatch = []
    samples = []
    total = 0
    for row in conn.execute("""
        SELECT id, payroll_run_id, gross_pay, total_deductions, net_pay
        FROM payroll_items ORDER BY id
    """):
        total += 1
        try:
            difference = cents(row["gross_pay"]) - cents(row["total_deductions"]) - cents(row["net_pay"])
        except ValueError:
            difference = None
        if difference is not None and abs(difference) <= 1:
            continue  # A one-cent rounding residue is recorded but not a blocker.
        mismatch.append(int(row["id"]))
        if len(samples) < limit:
            samples.append({
                "payroll_item_id": int(row["id"]),
                "payroll_run_id": int(row["payroll_run_id"]),
                "difference_centavos": difference,
            })
    return {
        "items_checked": total,
        "material_arithmetic_mismatch_count": len(mismatch),
        "mismatch_sample": samples,
        "sample_truncated": len(mismatch) > limit,
        "tolerance_centavos": 1,
    }


def check_versions(conn: sqlite3.Connection, limit: int) -> dict[str, Any]:
    runs = {
        int(row["id"]): dict(row)
        for row in conn.execute("""
            SELECT id, period_start, period_end, status, paid_at,
                   revision_of_run_id, revision_treatment, superseded_by_run_id
            FROM payroll_runs
        """)
    }
    problems: list[dict] = []
    classes = Counter()
    for run in runs.values():
        run_id = int(run["id"])
        parent_id = int(run["revision_of_run_id"] or 0)
        newer_id = int(run["superseded_by_run_id"] or 0)
        for related_id, relation in ((parent_id, "revision_parent"), (newer_id, "superseded_by")):
            if not related_id:
                continue
            if related_id == run_id:
                classes["self_reference"] += 1
                if len(problems) < limit:
                    problems.append({"run_id": run_id, "type": "self_reference", "relation": relation})
            elif related_id not in runs:
                classes["missing_related_run"] += 1
                if len(problems) < limit:
                    problems.append({"run_id": run_id, "type": "missing_related_run", "relation": relation, "related_run_id": related_id})
            else:
                linked = runs[related_id]
                if (run["period_start"], run["period_end"]) != (linked["period_start"], linked["period_end"]):
                    classes["different_coverage"] += 1
                    if len(problems) < limit:
                        problems.append({"run_id": run_id, "type": "different_coverage", "relation": relation, "related_run_id": related_id})
    return {
        "runs_checked": len(runs),
        "reference_review_count": sum(classes.values()),
        "by_reason": dict(classes),
        "sample": problems,
        "sample_truncated": sum(classes.values()) > limit,
    }


def check_statutory(conn: sqlite3.Connection, limit: int) -> dict[str, Any]:
    invalid = []
    receipt_keys: dict[tuple[str, str, str], list[int]] = {}
    recorded_centavos = Counter()
    count = 0
    for row in conn.execute("""
        SELECT id, program, contribution_month, payment_date, amount, reference
        FROM statutory_agency_remittances ORDER BY id
    """):
        count += 1
        program = str(row["program"] or "").lower()
        month = str(row["contribution_month"] or "")
        try:
            amount = cents(row["amount"])
        except ValueError:
            amount = 0
        if amount <= 0 or program not in ("sss", "philhealth", "pagibig") or len(month) != 7:
            if len(invalid) < limit:
                invalid.append(int(row["id"]))
        recorded_centavos[program] += amount
        reference = str(row["reference"] or "").strip().lower()
        if reference:
            receipt_keys.setdefault((program, month, reference), []).append(int(row["id"]))
    duplicates = [ids for ids in receipt_keys.values() if len(ids) > 1]
    orphan = [
        int(row[0]) for row in conn.execute("""
            SELECT sm.id FROM payroll_statutory_months sm
            LEFT JOIN payroll_runs pr ON pr.id=sm.payroll_run_id
            WHERE pr.id IS NULL ORDER BY sm.id LIMIT ?
        """, (limit,))
    ]
    orphan_total = int(conn.execute("""
        SELECT COUNT(*) FROM payroll_statutory_months sm
        LEFT JOIN payroll_runs pr ON pr.id=sm.payroll_run_id WHERE pr.id IS NULL
    """).fetchone()[0])
    return {
        "recorded_remittance_rows": count,
        "recorded_remittances_php_by_program": {
            key: recorded_centavos[key] / 100 for key in ("sss", "philhealth", "pagibig")
        },
        "invalid_remittance_sample_ids": invalid,
        "normalized_duplicate_receipt_groups": len(duplicates),
        "duplicate_receipt_ids_sample": duplicates[:limit],
        "orphan_statutory_month_count": orphan_total,
        "orphan_statutory_month_ids_sample": orphan,
        "recorded_does_not_prove_agency_received_funds": True,
    }


def backup_metadata(directory: Path, max_age_hours: int) -> dict[str, Any]:
    if not directory.is_dir():
        return {"backup_present": False, "backup_verified": False, "backup_age_within_limit": False}
    items = [
        item for item in directory.iterdir()
        if item.is_file() and item.name.startswith("staff-payroll-")
        and item.name.endswith(BACKUP_SUFFIXES)
    ]
    if not items:
        return {"backup_present": False, "backup_verified": False, "backup_age_within_limit": False}
    latest = max(items, key=lambda item: item.stat().st_mtime)
    age_hours = max(0, (time.time() - latest.stat().st_mtime) / 3600)
    return {
        "backup_present": True,
        "backup_verified": False,  # Metadata inspection is not a restore drill.
        "backup_count": len(items),
        "latest_backup_age_hours": round(age_hours, 1),
        "backup_age_within_limit": age_hours <= max_age_hours,
        "latest_backup_encrypted": latest.name.endswith(".fernet"),
        "offsite_destination_configured": bool(os.getenv("STAFF_PAYROLL_OFFSITE_BACKUP_DIR")),
        "offsite_copy_verified": False,
        "restore_drill_verified": False,
    }


def certify(conn: sqlite3.Connection, *, sample_limit: int = 10,
            backup_dir: Path | None = None, max_backup_age_hours: int = 26) -> dict[str, Any]:
    if sample_limit < 0:
        raise ValueError("sample_limit must be >= 0")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    blockers: list[str] = []
    reviews: list[str] = []
    missing_schema = {
        table: sorted(required - columns(conn, table))
        for table, required in REQUIRED.items()
        if required - columns(conn, table)
    }
    integrity = conn.execute("PRAGMA quick_check").fetchone()
    sqlite_integrity = bool(integrity and str(integrity[0]).lower() == "ok")
    foreign_key_count = sum(1 for _ in conn.execute("PRAGMA foreign_key_check"))
    if not sqlite_integrity:
        blockers.append("sqlite_quick_check_failed")
    if foreign_key_count:
        blockers.append("sqlite_foreign_key_violations")
    if missing_schema:
        blockers.append("missing_financial_schema")

    result: dict[str, Any] = {
        "read_only": True,
        "database_integrity_ok": sqlite_integrity,
        "foreign_key_violation_count": foreign_key_count,
        "missing_schema": missing_schema,
    }
    if not missing_schema:
        checks = (
            ("money_arithmetic", lambda: check_money(conn, sample_limit)),
            ("payroll_revision_references", lambda: check_versions(conn, sample_limit)),
            ("statutory_recorded_evidence", lambda: check_statutory(conn, sample_limit)),
            ("paid_adjustment_reversal_audit", lambda: audit_paid_adjustment_reversals(conn)),
            ("manual_repayment_outbox_audit", lambda: audit_manual_repayment_outbox(conn, sample_limit=sample_limit)),
        )
        for label, func in checks:
            try:
                result[label] = func()
            except (sqlite3.Error, RuntimeError, ValueError) as exc:
                blockers.append(f"{label}_unavailable")
                result[label] = {"error_type": type(exc).__name__}
        money = result.get("money_arithmetic", {})
        if money.get("material_arithmetic_mismatch_count", 0):
            blockers.append("payroll_net_pay_mismatch")
        versions = result.get("payroll_revision_references", {})
        if versions.get("reference_review_count", 0):
            reviews.append("payroll_revision_links_require_review")
        statutory = result.get("statutory_recorded_evidence", {})
        if statutory.get("invalid_remittance_sample_ids") or statutory.get("normalized_duplicate_receipt_groups") or statutory.get("orphan_statutory_month_count"):
            reviews.append("statutory_remittance_ledger_review")
        if result.get("paid_adjustment_reversal_audit", {}).get("finding_count", 0):
            reviews.append("potentially_reversed_paid_adjustment_repayments")
        manual = result.get("manual_repayment_outbox_audit", {})
        if manual.get("review_candidate_count") or manual.get("payment_method_review_count") or manual.get("possible_duplicate_groups_count"):
            reviews.append("manual_repayments_require_independent_cash_and_accounting_review")

    metadata = backup_metadata(backup_dir or Path(os.getenv("STAFF_PAYROLL_BACKUP_DIR", "backups")), max_backup_age_hours)
    result["backup_metadata"] = metadata
    if not metadata.get("backup_present") or not metadata.get("backup_age_within_limit"):
        reviews.append("backup_freshness_or_presence_requires_review")
    if metadata.get("backup_present") and not metadata.get("latest_backup_encrypted"):
        reviews.append("backup_encryption_requires_review")

    return {
        **result,
        "blocking_checks": sorted(set(blockers)),
        "human_review_checks": sorted(set(reviews)),
        "status": "blocked" if blockers else "review_required" if reviews else "local_checks_passed",
        "no_sqlite_writes": True,
        "accounting_imports_performed": False,
        "evidence_limitations": (
            "Staff records do not prove bank/cash receipts, Accounting postings, "
            "agency settlement, verified offsite backups, or a successful restore drill. "
            "Outbox delivery alone does not establish downstream posting. "
            "Do not auto-post, replay, reverse or settle money from this report."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(os.environ["STAFF_PAYROLL_DB_PATH"]) if os.getenv("STAFF_PAYROLL_DB_PATH") else None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-backup-age-hours", type=int, default=26)
    parser.add_argument("--strict-review", action="store_true", help="Also exit nonzero when a human review item exists.")
    args = parser.parse_args()
    if args.db is None or not args.db.is_absolute() or not args.db.is_file():
        parser.error("Specify an existing absolute SQLite database path")
    if args.limit < 0 or args.max_backup_age_hours < 1:
        parser.error("--limit must be nonnegative and --max-backup-age-hours positive")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        report = certify(conn, sample_limit=args.limit, backup_dir=args.backup_dir,
                         max_backup_age_hours=args.max_backup_age_hours)
    print(json.dumps(report, indent=2, default=str))
    return 2 if report["blocking_checks"] else (1 if args.strict_review and report["human_review_checks"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
