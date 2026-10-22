from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.certify_staff_operational_closeout import _release_evidence, closeout


def financial(*, blockers=None, reviews=None) -> dict:
    return {
        "blocking_checks": blockers or [],
        "human_review_checks": reviews or [],
        "status": "blocked" if blockers else "review_required",
        "money_arithmetic": {
            "items_checked": 7,
            "material_arithmetic_mismatch_count": int(bool(blockers)),
        },
    }


def repayment(*, passed=True, missing=0) -> dict:
    return {
        "passed": passed,
        "manual_repayment_count": 5,
        "manual_repayment_amount_php": 10500.0,
        "mismatch_count": int(not passed),
        "missing_staff_outbox_count": missing,
    }


class StaffCloseoutTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "staff.sqlite"
        with sqlite3.connect(self.db) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE sample (value INTEGER)")
            conn.execute("INSERT INTO sample VALUES(1)")

    def run_report(self, *, audit=None, parity=None, health=None, expected_sha=None):
        with sqlite3.connect(self.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            with patch("scripts.certify_staff_operational_closeout.certify", side_effect=audit or (lambda *_a, **_k: financial())), \
                 patch("scripts.certify_staff_operational_closeout.verify_review_queue", side_effect=parity or (lambda *_a, **_k: repayment())):
                return closeout(conn, live_health=health, expected_sha=expected_sha)

    def test_passed_staff_checks_never_claim_full_certification(self) -> None:
        result = self.run_report()
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["blocking_checks"], [])
        self.assertFalse(result["full_certification_claimed"])
        self.assertFalse(result["accounting_imports_performed"])
        self.assertFalse(result["historical_paid_payroll_changed"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["one_consistent_sqlite_snapshot"])
        self.assertIn("independent_offsite_backup_copy_and_restore_evidence", result["human_review_checks"])

    def test_detects_bad_money_and_unmatched_repayment_projection(self) -> None:
        report = self.run_report(
            audit=lambda *_a, **_k: financial(blockers=["payroll_net_pay_mismatch"]),
            parity=lambda *_a, **_k: repayment(passed=False, missing=2),
        )
        self.assertEqual(report["status"], "blocked")
        self.assertIn("payroll_net_pay_mismatch", report["blocking_checks"])
        self.assertIn("staff_repayment_handoff_projection_mismatch", report["blocking_checks"])
        self.assertIn("missing_historical_staff_outbox_requires_source_review", report["human_review_checks"])

    def test_release_evidence_requires_exact_agreement_and_authenticated_status(self) -> None:
        sha = "a" * 40
        live = {
            "ok": True,
            "release_verified": True,
            "deployed_sha": sha,
            "active_release_sha": sha,
            "running_api_sha": sha,
        }
        self.assertTrue(_release_evidence(live, sha)["verified"])
        self.assertFalse(_release_evidence(live, "b" * 40)["verified"])
        self.assertFalse(_release_evidence({**live, "running_api_sha": "b" * 40}, sha)["verified"])
        self.assertFalse(_release_evidence({**live, "release_verified": False}, sha)["verified"])
        self.assertFalse(_release_evidence(live, None)["verified"])
        self.assertFalse(_release_evidence(live, "A" * 40)["verified"])

    def test_invalid_health_identity_blocks_instead_of_claiming_safe_release(self) -> None:
        report = self.run_report(health={"ok": True, "release_verified": True}, expected_sha="a" * 40)
        self.assertIn("production_release_identity_mismatch", report["blocking_checks"])
        self.assertEqual(report["status"], "blocked")

    def test_single_read_snapshot_is_stable_during_concurrent_writer(self) -> None:
        seen = []

        def financial_audit(conn, **_kwargs):
            seen.append(conn.execute("SELECT value FROM sample").fetchone()[0])
            # WAL allows an independent writer without altering this audit's snapshot.
            with sqlite3.connect(self.db) as writer:
                writer.execute("UPDATE sample SET value=2")
            return financial()

        def repayment_audit(conn, **_kwargs):
            seen.append(conn.execute("SELECT value FROM sample").fetchone()[0])
            return repayment()

        self.run_report(audit=financial_audit, parity=repayment_audit)
        self.assertEqual(seen, [1, 1])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT value FROM sample").fetchone()[0], 2)

    def test_database_writes_are_rejected_and_reported_as_blocker(self) -> None:
        before = self.db.read_bytes()

        def faulty_audit(conn, **_kwargs):
            conn.execute("UPDATE sample SET value=999")
            return financial()

        report = self.run_report(audit=faulty_audit)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("financial_audit_unavailable", report["blocking_checks"])
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
