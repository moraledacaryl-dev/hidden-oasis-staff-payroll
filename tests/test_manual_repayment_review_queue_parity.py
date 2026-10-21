"""Read-only parity tests for Cash Advances review queue and outbox source."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.verify_manual_repayment_review_queue import verify_review_queue
from api.cash_advance_service import repayment_history


class RepaymentReviewQueueParityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / "staff.sqlite"
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
                CREATE TABLE cash_advance_repayments (
                    id INTEGER PRIMARY KEY, cash_advance_id INTEGER,
                    repayment_date TEXT, amount REAL, source TEXT,
                    payment_method TEXT, method TEXT, reference TEXT,
                    active INTEGER, payroll_run_id INTEGER, notes TEXT
                );
                CREATE TABLE payroll_runs (
                    id INTEGER PRIMARY KEY, status TEXT,
                    period_start TEXT, period_end TEXT
                );
                CREATE TABLE integration_outbox (
                    id INTEGER PRIMARY KEY, destination TEXT, event_type TEXT,
                    external_source TEXT, external_id TEXT, status TEXT
                );
                INSERT INTO payroll_runs VALUES
                    (7,'Paid','2026-09-01','2026-09-15');
                INSERT INTO cash_advance_repayments VALUES
                    (15,12,'2026-07-02',1000,'Manual','Cash','Cash','SECRET-RECEIPT-15',1,NULL,'SECRET'),
                    (29,21,'2026-08-03',500,'Manual','Cash','Cash',NULL,1,NULL,NULL),
                    (30,26,'2026-08-15',3000,'Manual','Other','Other',NULL,1,NULL,NULL),
                    (42,22,'2026-09-18',3000,'Manual','Cash','Cash',NULL,1,NULL,NULL),
                    (43,11,'2026-09-18',3000,'Manual','Cash','Cash',NULL,1,NULL,NULL),
                    (51,26,'2026-10-02',25,'Payroll','Payroll deduction','Payroll deduction',NULL,1,7,NULL),
                    (52,26,'2026-10-02',10,'Manual','Cash','Cash',NULL,0,NULL,NULL);
            """)

    def _verify(self, *, limit=30):
        with sqlite3.connect(self.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            return verify_review_queue(conn, sample_limit=limit)

    def test_all_five_historical_staff_repayments_match_missing_outbox_projection(self):
        before = self.db.read_bytes()
        data = self._verify()
        self.assertTrue(data["passed"])
        self.assertTrue(data["read_only"])
        self.assertEqual(data["manual_repayment_count"], 5)
        self.assertEqual(data["manual_repayment_amount_php"], 10500)
        self.assertEqual(data["ui_handoff_review_count"], 5)
        self.assertEqual(data["ui_handoff_review_amount_php"], 10500)
        self.assertEqual(data["missing_staff_outbox_count"], 5)
        self.assertEqual(data["mismatch_count"], 0)
        self.assertTrue(data["source_summary_matches"])
        self.assertFalse(data["accounting_posting_verified"])
        self.assertFalse(data["cash_custody_verified"])
        self.assertNotIn("SECRET", str(data))
        self.assertEqual(before, self.db.read_bytes())

    def test_queued_completed_retry_and_wrong_origin_are_not_confused(self):
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
                INSERT INTO integration_outbox VALUES
                    (1,'accounting','cash_advance.repaid',
                     'hidden_oasis_staff_payroll','cash-advance-repayment:15','Pending'),
                    (2,'accounting','cash_advance.repaid',
                     'hidden_oasis_staff_payroll','cash-advance-repayment:29','Completed'),
                    (3,'accounting','cash_advance.repaid',
                     'hidden_oasis_staff_payroll','cash-advance-repayment:30','Retry'),
                    (4,'operations','cash_advance.repaid',
                     'hidden_oasis_staff_payroll','cash-advance-repayment:42','Completed'),
                    (5,'accounting','cash_advance.repaid',
                     'another_app','cash-advance-repayment:43','Completed');
            """)
        data = self._verify()
        self.assertTrue(data["passed"])
        self.assertEqual(data["missing_staff_outbox_count"], 2)
        self.assertEqual(data["pending_delivery_count"], 1)
        self.assertEqual(data["delivered_posting_unverified_count"], 1)
        self.assertEqual(data["delivery_requires_review_count"], 1)
        self.assertEqual(data["ui_handoff_review_count"], 3)
        self.assertEqual(data["ui_handoff_review_amount_php"], 9000)
        self.assertEqual(data["mismatch_count"], 0)

    def test_detects_projection_drift_without_altering_record(self):
        from scripts import verify_manual_repayment_review_queue as module

        original = repayment_history

        def bad_projection(conn, advance_id):
            items = original(conn, advance_id)
            if advance_id == 12:
                for row in items:
                    if row["id"] == 15:
                        row["accounting_handoff_state"] = "delivered_posting_unverified"
            return items

        with patch.object(module, "repayment_history", side_effect=bad_projection):
            before = self.db.read_bytes()
            data = self._verify(limit=1)
            self.assertFalse(data["passed"])
            self.assertEqual(data["mismatch_count"], 1)
            self.assertEqual(data["mismatch_sample"][0]["repayment_id"], 15)
            self.assertEqual(data["mismatch_sample"][0]["reason"], "handoff_state_differs")
            self.assertEqual(before, self.db.read_bytes())

    def test_invalid_schema_and_limit_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "sample_limit"):
            self._verify(limit=-1)
        with sqlite3.connect(self.db) as conn:
            conn.execute("DROP TABLE integration_outbox")
        with self.assertRaisesRegex(RuntimeError, "integration_outbox"):
            self._verify()

    def test_zero_limit_reports_counts_without_ids(self):
        data = self._verify(limit=0)
        self.assertTrue(data["passed"])
        self.assertEqual(data["ui_handoff_review_count"], 5)
        self.assertEqual(data["mismatch_sample"], [])
        self.assertEqual(data["missing_from_projection_sample"], [])


if __name__ == "__main__":
    unittest.main()
