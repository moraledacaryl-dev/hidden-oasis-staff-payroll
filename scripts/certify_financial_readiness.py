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
from core.offsite_backups import S3_ENV_NAMES

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
    "payroll_statutory_months": {
        "id", "payroll_run_id", "month_start", "sss_ee", "sss_er", "sss_ec",
        "philhealth_ee", "philhealth_er", "pagibig_ee", "pagibig_er",
    },
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
    invalid_count = 0
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
            invalid_count += 1
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
    # Statutory totals are only recognized from active Paid/Locked snapshots.
    # A zero sum is incomplete evidence if there are historical payroll runs
    # with missing snapshots or no finalized statuses.
    status_counts_all = {
        str(row["status"] or "(blank)"): int(row["count"])
        for row in conn.execute(
            "SELECT status, COUNT(*) AS count FROM payroll_runs GROUP BY status"
        )
    }
    status_counts_current: Counter[str] = Counter()
    current_runs = 0
    settled_runs = 0
    settled_runs_with_items = 0
    settled_runs_with_snapshots = 0
    missing_snapshot_count = 0
    missing_snapshot_sample: list[int] = []
    inconsistent_paid_metadata_count = 0
    inconsistent_paid_metadata_sample: list[int] = []
    for row in conn.execute("""
        SELECT pr.id, pr.status, pr.paid_at,
               (SELECT COUNT(*) FROM payroll_items pi WHERE pi.payroll_run_id=pr.id) AS item_count,
               (SELECT COUNT(*) FROM payroll_statutory_months sm WHERE sm.payroll_run_id=pr.id) AS snapshot_count
        FROM payroll_runs pr
        WHERE COALESCE(pr.superseded_by_run_id,0)=0
        ORDER BY pr.id
    """):
        current_runs += 1
        run_id = int(row["id"])
        state = str(row["status"] or "(blank)")
        status_counts_current[state] += 1
        is_settled = state in {"Paid", "Locked"}
        item_count = int(row["item_count"] or 0)
        snapshot_count = int(row["snapshot_count"] or 0)
        if is_settled:
            settled_runs += 1
            settled_runs_with_items += bool(item_count)
            settled_runs_with_snapshots += bool(snapshot_count)
            if item_count and not snapshot_count:
                missing_snapshot_count += 1
                if len(missing_snapshot_sample) < limit:
                    missing_snapshot_sample.append(run_id)
        elif row["paid_at"]:
            # Historical states may be valid, but require an operator to check
            # before concluding that "no recognized liability" is factual.
            inconsistent_paid_metadata_count += 1
            if len(inconsistent_paid_metadata_sample) < limit:
                inconsistent_paid_metadata_sample.append(run_id)
    total_snapshot_rows = int(conn.execute(
        "SELECT COUNT(*) FROM payroll_statutory_months"
    ).fetchone()[0])
    obligations = conn.execute("""
        SELECT COUNT(DISTINCT sm.payroll_run_id) AS recognized_payroll_runs,
               COALESCE(SUM(COALESCE(sm.sss_ee,0)+COALESCE(sm.sss_er,0)+COALESCE(sm.sss_ec,0)),0) AS sss,
               COALESCE(SUM(COALESCE(sm.philhealth_ee,0)+COALESCE(sm.philhealth_er,0)),0) AS philhealth,
               COALESCE(SUM(COALESCE(sm.pagibig_ee,0)+COALESCE(sm.pagibig_er,0)),0) AS pagibig
        FROM payroll_statutory_months sm
        JOIN payroll_runs pr ON pr.id=sm.payroll_run_id
        WHERE pr.status IN ('Paid','Locked')
          AND COALESCE(pr.superseded_by_run_id,0)=0
    """).fetchone()
    obligation_cents = {
        program: cents(obligations[program])
        for program in ("sss", "philhealth", "pagibig")
    }
    missing_evidence = [
        program for program in ("sss", "philhealth", "pagibig")
        if obligation_cents[program] > recorded_centavos[program]
    ]
    return {
        "recorded_remittance_rows": count,
        "payroll_run_status_counts_all": status_counts_all,
        "current_payroll_run_status_counts": dict(status_counts_current),
        "current_payroll_runs": current_runs,
        "current_paid_or_locked_runs": settled_runs,
        "current_paid_or_locked_runs_with_payroll_items": settled_runs_with_items,
        "current_paid_or_locked_runs_with_snapshots": settled_runs_with_snapshots,
        "current_paid_or_locked_runs_missing_snapshots": missing_snapshot_count,
        "current_paid_or_locked_missing_snapshot_ids_sample": missing_snapshot_sample,
        "current_paid_or_locked_missing_snapshot_sample_truncated": missing_snapshot_count > limit,
        "current_nonsettled_runs_with_paid_at": inconsistent_paid_metadata_count,
        "current_nonsettled_paid_at_ids_sample": inconsistent_paid_metadata_sample,
        "current_nonsettled_paid_at_sample_truncated": inconsistent_paid_metadata_count > limit,
        "all_statutory_snapshot_rows": total_snapshot_rows,
        "zero_recognized_contributions_needs_source_status_review": settled_runs == 0 and current_runs > 0,
        "recognized_payroll_runs_with_statutory_snapshots": int(obligations["recognized_payroll_runs"] or 0),
        "recognized_obligations_php_by_program": {
            program: obligation_cents[program] / 100
            for program in ("sss", "philhealth", "pagibig")
        },
        "insufficient_staff_remittance_evidence_for_programs": missing_evidence,
        "external_agency_receipts_not_examined": True,
        "invalid_remittance_count": invalid_count,
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


def offsite_configuration_status() -> str:
    """Return sanitized destination type, never exposing credentials or URLs."""
    if os.getenv("STAFF_PAYROLL_OFFSITE_BACKUP_DIR", "").strip():
        return "directory_configured"
    s3_fields = [bool(os.getenv(name, "").strip()) for name in S3_ENV_NAMES]
    if all(s3_fields):
        return "s3_configured_not_verified"
    if any(s3_fields):
        return "s3_configuration_incomplete"
    return "not_configured"


def backup_metadata(directory: Path, max_age_hours: int) -> dict[str, Any]:
    offsite_status = offsite_configuration_status()
    base = {
        "backup_verified": False,
        "offsite_configuration_status": offsite_status,
        "offsite_destination_configured": offsite_status in {"directory_configured", "s3_configured_not_verified"},
        "offsite_copy_verified": False,
        "restore_drill_verified": False,
    }
    if not directory.is_dir():
        return {**base, "backup_present": False, "backup_age_within_limit": False}
    items = [
        item for item in directory.iterdir()
        if item.is_file() and item.name.startswith("staff-payroll-")
        and item.name.endswith(BACKUP_SUFFIXES)
    ]
    if not items:
        return {**base, "backup_present": False, "backup_age_within_limit": False}
    latest = max(items, key=lambda item: item.stat().st_mtime)
    age_hours = max(0, (time.time() - latest.stat().st_mtime) / 3600)
    return {
        **base,
        "backup_present": True,
        "backup_verified": False,  # Metadata inspection is not a restore drill.
        "backup_count": len(items),
        "latest_backup_age_hours": round(age_hours, 1),
        "backup_age_within_limit": age_hours <= max_age_hours,
        "latest_backup_encrypted": latest.name.endswith(".fernet"),
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
        if statutory.get("invalid_remittance_count") or statutory.get("normalized_duplicate_receipt_groups") or statutory.get("orphan_statutory_month_count"):
            reviews.append("statutory_remittance_ledger_review")
        if statutory.get("insufficient_staff_remittance_evidence_for_programs"):
            reviews.append("statutory_obligations_need_external_remittance_reconciliation")
        if statutory.get("current_paid_or_locked_runs_missing_snapshots"):
            reviews.append("settled_payroll_missing_statutory_snapshots")
        if statutory.get("current_nonsettled_runs_with_paid_at"):
            reviews.append("paid_payroll_status_and_timestamp_require_review")
        if statutory.get("zero_recognized_contributions_needs_source_status_review"):
            reviews.append("no_paid_or_locked_runs_for_statutory_recognition")
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
    if metadata.get("offsite_configuration_status") in ("not_configured", "s3_configuration_incomplete"):
        reviews.append("offsite_backup_configuration_requires_review")
    # This command inspects metadata only; it cannot certify offsite parity
    # or successful restore. Leave this as a separate, explicit review gate.
    reviews.append("backup_restore_and_offsite_evidence_not_verified")

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
