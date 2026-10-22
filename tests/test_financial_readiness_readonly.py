from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.certify_financial_readiness import backup_metadata, certify, offsite_configuration_status


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
                    id INTEGER PRIMARY KEY, payroll_run_id INTEGER, month_start TEXT,
                    sss_ee REAL DEFAULT 0, sss_er REAL DEFAULT 0, sss_ec REAL DEFAULT 0,
                    philhealth_ee REAL DEFAULT 0, philhealth_er REAL DEFAULT 0,
                    pagibig_ee REAL DEFAULT 0, pagibig_er REAL DEFAULT 0
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
        self.assertIn("backup_restore_and_offsite_evidence_not_verified", report["human_review_checks"])
        self.assertEqual(report["status"], "review_required")
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

    def test_recognized_contributions_without_staff_receipts_trigger_external_review(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """UPDATE payroll_statutory_months
                   SET sss_ee=160, sss_er=40, sss_ec=10,
                       philhealth_ee=30, philhealth_er=30,
                       pagibig_ee=50, pagibig_er=50
                   WHERE id=1"""
            )
        report = self.run_audit()
        obligations = report["statutory_recorded_evidence"]
        self.assertEqual(obligations["recognized_payroll_runs_with_statutory_snapshots"], 1)
        self.assertEqual(obligations["recognized_obligations_php_by_program"], {
            "sss": 210.0, "philhealth": 60.0, "pagibig": 100.0
        })
        self.assertEqual(
            obligations["insufficient_staff_remittance_evidence_for_programs"],
            ["sss", "philhealth", "pagibig"],
        )
        self.assertIn(
            "statutory_obligations_need_external_remittance_reconciliation",
            report["human_review_checks"],
        )
        self.assertNotIn(
            "statutory_obligations_need_external_remittance_reconciliation",
            report["blocking_checks"],
        )

    def test_draft_and_superseded_payroll_do_not_create_recognized_obligations(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE payroll_runs SET status='Draft' WHERE id=1"
            )
            conn.execute("UPDATE payroll_statutory_months SET sss_ee=1000 WHERE id=1")
        report = self.run_audit()
        statutory = report["statutory_recorded_evidence"]
        self.assertEqual(statutory["recognized_obligations_php_by_program"]["sss"], 0)
        self.assertEqual(statutory["recognized_payroll_runs_with_statutory_snapshots"], 0)
        self.assertNotIn(
            "statutory_obligations_need_external_remittance_reconciliation",
            report["human_review_checks"],
        )

    def test_s3_offsite_configuration_is_recognized_without_leaking_credentials(self) -> None:
        values = {
            "STAFF_PAYROLL_OFFSITE_BACKUP_DIR": "",
            "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "https://backup.example.test",
            "STAFF_PAYROLL_OFFSITE_S3_BUCKET": "private-bucket",
            "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID": "PRIVATE_ACCESS_ID",
            "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY": "PRIVATE_SECRET",
        }
        with patch.dict(os.environ, values):
            result = backup_metadata(self.backup_dir, 26)
        self.assertEqual(result["offsite_configuration_status"], "s3_configured_not_verified")
        self.assertTrue(result["offsite_destination_configured"])
        self.assertFalse(result["offsite_copy_verified"])
        self.assertNotIn("PRIVATE_SECRET", str(result))
        self.assertNotIn("PRIVATE_ACCESS_ID", str(result))
        self.assertNotIn("private-bucket", str(result))

    def test_partial_s3_configuration_is_review_not_proof_of_offsite(self) -> None:
        values = {
            "STAFF_PAYROLL_OFFSITE_BACKUP_DIR": "",
            "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "https://backup.example.test",
            "STAFF_PAYROLL_OFFSITE_S3_BUCKET": "",
            "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID": "",
            "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY": "",
        }
        with patch.dict(os.environ, values):
            result = self.run_audit()
        self.assertEqual(result["backup_metadata"]["offsite_configuration_status"], "s3_configuration_incomplete")
        self.assertIn("offsite_backup_configuration_requires_review", result["human_review_checks"])

    def test_paid_payroll_without_snapshots_is_reviewed_not_assumed_zero_liability(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM payroll_statutory_months WHERE payroll_run_id=1")
        report = self.run_audit()
        statutory = report["statutory_recorded_evidence"]
        self.assertEqual(statutory["current_paid_or_locked_runs"], 1)
        self.assertEqual(statutory["current_paid_or_locked_runs_with_payroll_items"], 1)
        self.assertEqual(statutory["current_paid_or_locked_runs_with_snapshots"], 0)
        self.assertEqual(statutory["current_paid_or_locked_runs_missing_snapshots"], 1)
        self.assertEqual(statutory["current_paid_or_locked_missing_snapshot_ids_sample"], [1])
        self.assertEqual(statutory["recognized_obligations_php_by_program"]["sss"], 0)
        self.assertIn("settled_payroll_missing_statutory_snapshots", report["human_review_checks"])
        self.assertEqual(report["blocking_checks"], [])

    def test_no_settled_run_is_explicit_evidence_gap_not_zero_obligation_proof(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_runs SET status='Draft', paid_at=NULL WHERE id=1")
        report = self.run_audit()
        statutory = report["statutory_recorded_evidence"]
        self.assertEqual(statutory["current_paid_or_locked_runs"], 0)
        self.assertEqual(statutory["payroll_run_status_counts_all"]["Draft"], 1)
        self.assertEqual(statutory["current_payroll_run_status_counts"]["Draft"], 1)
        self.assertTrue(statutory["zero_recognized_contributions_needs_source_status_review"])
        self.assertIn("no_paid_or_locked_runs_for_statutory_recognition", report["human_review_checks"])
        self.assertNotIn("settled_payroll_missing_statutory_snapshots", report["human_review_checks"])

    def test_paid_timestamp_on_unsettled_status_requires_independent_review(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=1")
        report = self.run_audit()
        statutory = report["statutory_recorded_evidence"]
        self.assertEqual(statutory["current_nonsettled_runs_with_paid_at"], 1)
        self.assertEqual(statutory["current_nonsettled_paid_at_ids_sample"], [1])
        self.assertIn("paid_payroll_status_and_timestamp_require_review", report["human_review_checks"])

    def test_superseded_paid_run_is_excluded_from_active_snapshot_coverage(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """INSERT INTO payroll_runs(
                    id,period_start,period_end,status,paid_at,revision_of_run_id
                ) VALUES(2,'2026-10-01','2026-10-14','Draft',NULL,1)"""
            )
            conn.execute("UPDATE payroll_runs SET superseded_by_run_id=2 WHERE id=1")
            conn.execute("INSERT INTO payroll_items VALUES(2,2,2000,400,1600)")
        report = self.run_audit()
        statutory = report["statutory_recorded_evidence"]
        self.assertEqual(statutory["current_payroll_runs"], 1)
        self.assertEqual(statutory["current_paid_or_locked_runs"], 0)
        self.assertEqual(statutory["all_statutory_snapshot_rows"], 1)
        self.assertEqual(statutory["payroll_run_status_counts_all"], {"Draft": 1, "Paid": 1})
        self.assertEqual(statutory["current_payroll_run_status_counts"], {"Draft": 1})
        self.assertIn("no_paid_or_locked_runs_for_statutory_recognition", report["human_review_checks"])

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
