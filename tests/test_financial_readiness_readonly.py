from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.certify_financial_readiness import backup_metadata, certify


class FinancialReadinessReadOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "staff.sqlite"
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir()
        self.backup = self.backup_dir / "staff-payroll-package-example.zip.fernet"
        self.backup.write_bytes(b"metadata only, not a verified backup")
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE payroll_runs (
                    id INTEGER PRIMARY KEY, period_start TEXT, period_end TEXT,
                    status TEXT, paid_at TEXT, revision_of_run_id INTEGER,
                    revision_treatment TEXT, superseded_by_run_id INTEGER
                );
                CREATE TABLE payroll_items (
                    id INTEGER PRIMARY KEY, payroll_run_id INTEGER,
                    gross_pay REAL, total_deductions REAL, net_pay REAL
                );
                CREATE TABLE cash_advances (id INTEGER PRIMARY KEY);
                CREATE TABLE cash_advance_repayments (
                    id INTEGER PRIMARY KEY, cash_advance_id INTEGER,
                    payroll_run_id INTEGER, amount REAL, active INTEGER,
                    reversal_reason TEXT, reversed_at TEXT, source TEXT,
                    repayment_date TEXT, payment_method TEXT, method TEXT,
                    reference TEXT
                );
                CREATE TABLE integration_outbox (
                    id INTEGER PRIMARY KEY, destination TEXT, event_type TEXT,
                    external_source TEXT, external_id TEXT, status TEXT
                );
                CREATE TABLE statutory_agency_remittances (
                    id INTEGER PRIMARY KEY, program TEXT, contribution_month TEXT,
                    payment_date TEXT, amount REAL, reference TEXT
                );
                CREATE TABLE payroll_statutory_months (
                    id INTEGER PRIMARY KEY, payroll_run_id INTEGER, month_start TEXT
                );
                INSERT INTO payroll_runs(id,period_start,period_end,status,paid_at)
                VALUES(1,'2026-10-01','2026-10-14','Paid','2026-10-15');
                INSERT INTO payroll_items(id,payroll_run_id,gross_pay,total_deductions,net_pay)
                VALUES(1,1,2000,400,1600);
                INSERT INTO cash_advances(id) VALUES(100);
                INSERT INTO payroll_statutory_months(id,payroll_run_id,month_start)
                VALUES(1,1,'2026-10-01');
                INSERT INTO statutory_agency_remittances(
                    id,program,contribution_month,payment_date,amount,reference
                ) VALUES(1,'sss','2026-10','2026-10-18',100,'Receipt-A');
            """)

    def run_audit(self, backup_dir: Path | None = None):
        # Connecting with mode=ro, plus PRAGMA query_only, preserves money ledgers.
        with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            return certify(conn, backup_dir=backup_dir or self.backup_dir, sample_limit=3)

    def test_healthy_ledger_returns_pass_without_claiming_downstream_posting(self) -> None:
        report = self.run_audit()
        self.assertEqual(report["blocking_checks"], [])
        self.assertEqual(report["human_review_checks"], [])
        self.assertEqual(report["status"], "local_checks_passed")
        self.assertEqual(report["money_arithmetic"]["items_checked"], 1)
        self.assertTrue(report["read_only"])
        self.assertTrue(report["no_sqlite_writes"])
        self.assertFalse(report["accounting_imports_performed"])
        self.assertFalse(report["backup_metadata"]["backup_verified"])
        self.assertFalse(report["backup_metadata"]["offsite_copy_verified"])

    def test_incorrect_net_pay_blocks_certification_without_mutation(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_items SET net_pay=1500 WHERE id=1")
        before = self.path.read_bytes()
        report = self.run_audit()
        self.assertIn("payroll_net_pay_mismatch", report["blocking_checks"])
        self.assertEqual(report["money_arithmetic"]["mismatch_sample"][0]["difference_centavos"], 10000)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_financial_schema_fails_closed_not_empty_pass(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE payroll_statutory_months")
        report = self.run_audit()
        self.assertIn("missing_financial_schema", report["blocking_checks"])
        self.assertIn("payroll_statutory_months", report["missing_schema"])
        self.assertNotIn("manual_repayment_outbox_audit", report)

    def test_dangling_revision_is_review_not_automatic_financial_reversal(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_runs SET revision_of_run_id=999 WHERE id=1")
        report = self.run_audit()
        self.assertEqual(report["status"], "review_required")
        self.assertIn("payroll_revision_links_require_review", report["human_review_checks"])
        self.assertEqual(report["payroll_revision_references"]["by_reason"]["missing_related_run"], 1)

    def test_missing_manual_outbox_is_review_not_assumed_missing_bank_receipt(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """INSERT INTO cash_advance_repayments(
                    id,cash_advance_id,payroll_run_id,amount,active,source,
                    repayment_date,payment_method,method,reference
                ) VALUES(20,100,NULL,500,1,'Manual','2026-10-19','GCash',NULL,'private-value')"""
            )
        report = self.run_audit()
        self.assertEqual(report["status"], "review_required")
        self.assertNotIn("manual_repayments_require_independent_cash_and_accounting_review", report["blocking_checks"])
        self.assertIn("manual_repayments_require_independent_cash_and_accounting_review", report["human_review_checks"])
        # Never print the sensitive receipt reference in audit output.
        self.assertNotIn("private-value", str(report))

    def test_duplicated_statutory_receipt_flagged_for_review_not_paid_twice(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """INSERT INTO statutory_agency_remittances(
                    id,program,contribution_month,payment_date,amount,reference
                ) VALUES(2,'sss','2026-10','2026-10-19',100,' receipt-a ')"""
            )
        report = self.run_audit()
        self.assertIn("statutory_remittance_ledger_review", report["human_review_checks"])
        self.assertEqual(report["statutory_recorded_evidence"]["normalized_duplicate_receipt_groups"], 1)
        self.assertEqual(report["statutory_recorded_evidence"]["recorded_remittances_php_by_program"]["sss"], 200)

    def test_backup_metadata_never_claims_restore_proven(self) -> None:
        result = backup_metadata(self.backup_dir, max_age_hours=26)
        self.assertTrue(result["backup_present"])
        self.assertFalse(result["backup_verified"])
        self.assertFalse(result["restore_drill_verified"])
        self.assertTrue(result["latest_backup_encrypted"])

    def test_stale_backup_creates_review_flag(self) -> None:
        stale = time.time() - 72 * 3600
        os.utime(self.backup, (stale, stale))
        report = self.run_audit()
        self.assertEqual(report["status"], "review_required")
        self.assertIn("backup_freshness_or_presence_requires_review", report["human_review_checks"])

    def test_invalid_amount_is_a_blocker_without_crash(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_items SET net_pay='NaN' WHERE id=1")
        report = self.run_audit()
        self.assertIn("payroll_net_pay_mismatch", report["blocking_checks"])
        self.assertIsNone(report["money_arithmetic"]["mismatch_sample"][0]["difference_centavos"])


if __name__ == "__main__":
    unittest.main()
