#!/usr/bin/env python3
"""Fail-closed, read-only Staff financial and operational closeout worklist.

Combines existing immutable-ledger audits on one SQLite read snapshot.
This tool cannot certify cash custody, Accounting posting, agency payment,
offsite restore or live service health on its own. It performs no writes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from scripts.certify_financial_readiness import certify
from scripts.verify_manual_repayment_review_queue import verify_review_queue

SHA = re.compile(r"[a-f0-9]{40}\\Z")
INDEPENDENT_GATES = (
    "cash_receipts_and_original_employee_payslips_review",
    "accounting_posting_and_bank_custody_review",
    "official_agency_remittance_receipts_review",
    "independent_offsite_backup_copy_and_restore_evidence",
    "live_api_web_and_worker_service_verification",
)


def _release_evidence(health: dict[str, Any] | None, expected_sha: str | None) -> dict[str, Any]:
    if health is None:
        return {
            "status": "not_supplied",
            "verified": False,
            "reason": "An independent authenticated live production health snapshot is required.",
        }
    if not isinstance(health, dict):
        return {"status": "invalid", "verified": False, "reason": "Expected a health object."}
    shas = [health.get(key) for key in ("deployed_sha", "active_release_sha", "running_api_sha")]
    valid = all(isinstance(s, str) and SHA.fullmatch(s) for s in shas)
    agreement = bool(valid and shas[0] == shas[1] == shas[2])
    expected = bool(expected_sha and agreement and shas[0] == expected_sha)
    verified = bool(health.get("ok") is True and health.get("release_verified") is True and expected)
    return {
        "status": "sha_verified" if verified else "unverified_or_mismatch",
        "verified": verified,
        "expected_sha": expected_sha,
        "reported_sha": shas[0] if valid else None,
        "source": "operator_supplied_authenticated_production_health_snapshot",
        "limitation": "JSON provenance and running web/worker service state still require independent verification.",
    }


def closeout(
    conn: sqlite3.Connection, *,
    sample_limit: int = 10,
    backup_dir: Path | None = None,
    live_health: dict[str, Any] | None = None,
    expected_sha: str | None = None,
) -> dict[str, Any]:
    if sample_limit < 0:
        raise ValueError("sample_limit must be nonnegative")
    if expected_sha is not None and not SHA.fullmatch(expected_sha):
        raise ValueError("expected_sha must contain exactly 40 lowercase hex digits")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    if not conn.in_transaction:
        conn.execute("BEGIN")
    blockers: list[str] = []
    reviews: list[str] = []

    try:
        finance = certify(conn, sample_limit=sample_limit, backup_dir=backup_dir)
        blockers.extend(finance["blocking_checks"])
        reviews.extend(finance["human_review_checks"])
        financial_status = finance["status"]
        financial_summary = {
            "status": financial_status,
            "money_items_checked": finance.get("money_arithmetic", {}).get("items_checked"),
            "material_arithmetic_mismatch_count": finance.get("money_arithmetic", {}).get("material_arithmetic_mismatch_count"),
            "human_review_checks": finance["human_review_checks"],
        }
    except Exception as exc:
        blockers.append("financial_audit_unavailable")
        financial_summary = {"status": "unavailable", "error_type": type(exc).__name__}

    try:
        parity = verify_review_queue(conn, sample_limit=sample_limit)
        if parity.get("passed") is not True:
            blockers.append("staff_repayment_handoff_projection_mismatch")
        parity_summary = {
            "passed": parity.get("passed") is True,
            "manual_repayment_count": parity.get("manual_repayment_count"),
            "manual_repayment_amount_php": parity.get("manual_repayment_amount_php"),
            "mismatch_count": parity.get("mismatch_count"),
            "missing_staff_outbox_count": parity.get("missing_staff_outbox_count"),
            "cash_custody_verified": False,
            "accounting_posting_verified": False,
        }
        if parity.get("missing_staff_outbox_count"):
            reviews.append("missing_historical_staff_outbox_requires_source_review")
    except Exception as exc:
        blockers.append("repayment_projection_audit_unavailable")
        parity_summary = {"passed": False, "error_type": type(exc).__name__}

    release = _release_evidence(live_health, expected_sha)
    if release["status"] == "unverified_or_mismatch":
        blockers.append("production_release_identity_mismatch")
    elif not release["verified"]:
        reviews.append("production_release_identity_requires_independent_verification")

    # This is a worklist, never a financial or disaster-recovery certificate.
    # No user-supplied JSON, Staff event status or local config proves these.
    reviews.extend(INDEPENDENT_GATES)
    return {
        "read_only": True,
        "one_consistent_sqlite_snapshot": conn.in_transaction,
        "accounting_imports_performed": False,
        "historical_paid_payroll_changed": False,
        "financial": financial_summary,
        "staff_manual_repayment_projection": parity_summary,
        "production_release": release,
        "blocking_checks": sorted(set(blockers)),
        "human_review_checks": sorted(set(reviews)),
        "status": "blocked" if blockers else "review_required",
        "full_certification_claimed": False,
        "interpretation": (
            "Passing local parity is not proof of bank receipts, agency settlement, "
            "Accounting posting, offsite recovery or employee payslip accuracy. "
            "Resolve independent evidence before declaring operational closeout."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path,
                        default=Path(os.environ["STAFF_PAYROLL_DB_PATH"])
                        if os.environ.get("STAFF_PAYROLL_DB_PATH") else None)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--live-health-json", type=Path, help="Operator-exported authenticated live API health JSON, never secrets")
    parser.add_argument("--expected-sha", type=str)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.db is None or not args.db.is_absolute() or not args.db.is_file():
        parser.error("Provide an existing absolute Staff SQLite path")
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    if args.expected_sha is not None and not SHA.fullmatch(args.expected_sha):
        parser.error("--expected-sha must be a 40-character lowercase hex SHA")
    try:
        health = json.loads(args.live_health_json.read_text(encoding="utf-8")) if args.live_health_json else None
    except (OSError, ValueError) as exc:
        parser.error("Cannot read valid health JSON: " + type(exc).__name__)
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        result = closeout(conn, sample_limit=args.limit, backup_dir=args.backup_dir,
                          live_health=health, expected_sha=args.expected_sha)
    print(json.dumps(result, indent=2))
    return 2 if result["blocking_checks"] else 1  # review always remains required


if __name__ == "__main__":
    raise SystemExit(main())
