"""Read-only historical manual repayment ledger context regression tests."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.audit_manual_repayment_ledger_context import audit_ledger


class HistoricalManualRepaymentLedgerContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "staff.sqlite"
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE cash_advances(
                    id INTEGER PRIMARY KEY, amount REAL,
                    ledger_opening_balance REAL, remaining_balance REAL,
                    outstanding_balance REAL, status TEXT
                );
                CREATE TABLE cash_advance_repayments(
                    id INTEGER PRIMARY KEY, cash_advance_id INTEGER,
                    source TEXT, amount REAL, repayment_date TEXT, active INTEGER,
                    payroll_run_id INTEGER, payment_method TEXT, method TEXT,
                    reference TEXT, notes TEXT
                );
                CREATE TABLE payroll_runs(
                    id INTEGER PRIMARY KEY, status TEXT
                );
                CREATE TABLE integration_outbox(
                    id INTEGER PRIMARY KEY, destination TEXT,
                    external_source TEXT, event_type TEXT, external_id TEXT
                );
                INSERT INTO cash_advances VALUES
                    (12,2000,2000,250,250,'Partially Paid'),
                    (21,5000,4000,3500,3500,'Partially Paid'),
                    (26,3000,3000,0,0,'Fully Paid'),
                    (22,3000,3000,0,0,'Fully Paid'),
                    (11,3000,3000,0,0,'Fully Paid'),
                    (99,700,700,400,400,'Partially Paid');
                INSERT INTO payroll_runs VALUES (7,'Paid'),(8,'Draft');
                INSERT INTO cash_advance_repayments VALUES
                    (15,12,'Manual',1000,'2026-07-02',1,NULL,'Cash','Cash','SENSITIVE-15','private'),
                    (29,21,'Manual',500,'2026-08-03',1,NULL,'Cash','Cash',NULL,NULL),
                    (30,26,'Manual',3000,'2026-08-15',1,NULL,'Other','Other','SENSITIVE-30',NULL),
                    (42,22,'Manual',3000,'2026-09-18',1,NULL,'Cash','Cash',NULL,NULL),
                    (43,11,'Manual',3000,'2026-09-18',1,NULL,'Cash','Cash',NULL,NULL),
                    (66,12,'Payroll',750,'2026-06-30',1,7,'Payroll Deduction',NULL,NULL,NULL),
                    (67,26,'Payroll',50,'2026-08-15',0,7,'Payroll Deduction',NULL,NULL,NULL),
                    (68,26,'Payroll',400,'2026-08-16',1,8,'Payroll Deduction',NULL,NULL,NULL),
                    (69,99,'Manual',300,'2026-08-18',1,NULL,'Cash','Cash',NULL,NULL);
                INSERT INTO integration_outbox VALUES
                    (1,'accounting','hidden_oasis_staff_payroll',
                     'cash_advance.repaid','cash-advance-repayment:69');
            """)

    def _audit(self, limit=30):
        with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            return audit_ledger(db, sample_limit=limit)

    def test_five_targets_and_rollforward_arithmetic(self):
        before = self.path.read_bytes()
        report = self._audit()
        self.assertTrue(report["read_only"])
        self.assertEqual(report["repayment_count"], 5)
        self.assertEqual(report["total_repayment_php"], 10500.0)
        self.assertEqual(report["cases_with_ledger_or_method_review_flags"], 1)
        cases = {x["repayment_id"]: x for x in report["cases"]}
        self.assertEqual(set(cases), {15,29,30,42,43})
        self.assertEqual(cases[15]["active_manual_repaid_php"], 1000.0)
        self.assertEqual(cases[15]["confirmed_payroll_deductions_php"], 750.0)
        self.assertEqual(cases[15]["calculated_remaining_php"], 250.0)
        self.assertEqual(cases[21 if 21 in cases else 29]["ledger_opening_php"], 4000.0)
        self.assertEqual(cases[29]["stored_remaining_php"], 3500.0)
        self.assertEqual(cases[30]["unconfirmed_payroll_repayments_php"], 400.0)
        self.assertEqual(cases[30]["inactive_repayment_amount_php"], 50.0)
        self.assertEqual(cases[30]["calculated_remaining_php"], 0.0)
        self.assertEqual(cases[30]["review_flags"], ["payment_method_needs_verification"])
        self.assertFalse(cases[30]["cash_receipt_independently_verified"])
        self.assertEqual(report["shared_date_amount_across_advances_count"], 1)
        self.assertEqual(report["shared_date_amount_across_advances"][0]["repayment_ids"], [42,43])
        self.assertEqual(report["shared_date_amount_across_advances"][0]["cash_advance_ids"], [11,22])
        self.assertNotIn("SENSITIVE", str(report))
        self.assertNotIn("private", str(report))
        self.assertEqual(self.path.read_bytes(), before)

    def test_stored_balance_discrepancy_is_flagged_but_not_repaired(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE cash_advances SET remaining_balance=300 WHERE id=12")
        before = self.path.read_bytes()
        report = self._audit(limit=1)
        self.assertEqual(report["cases"][0]["repayment_id"], 15)
        self.assertIn("stored_remaining_differs_from_calculated", report["cases"][0]["review_flags"])
        self.assertEqual(report["cases"][0]["calculated_remaining_php"], 250.0)
        self.assertEqual(report["cases"][0]["stored_remaining_php"], 300.0)
        self.assertEqual(report["repayment_count"], 5)
        self.assertTrue(report["sample_truncated"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_zero_limit_only_reports_counts_not_advance_details(self):
        report = self._audit(limit=0)
        self.assertEqual(report["repayment_count"], 5)
        self.assertEqual(report["cases"], [])
        self.assertEqual(report["shared_date_amount_across_advances"], [])
        self.assertEqual(report["shared_date_amount_across_advances_count"], 1)

    def test_missing_schema_fails_closed_instead_of_reporting_clean(self):
        with sqlite3.connect(":memory:") as db:
            with self.assertRaisesRegex(RuntimeError, "missing columns"):
                audit_ledger(db)


if __name__ == "__main__":
    unittest.main()
