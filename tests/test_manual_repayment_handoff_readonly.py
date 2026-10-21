"""Cash-advance repayment history must not equate Staff delivery to Accounting posting."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from api.cash_advance_service import repayment_history


class ManualRepaymentHandoffReadonlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "staff.sqlite"
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE cash_advance_repayments (
                    id INTEGER PRIMARY KEY,
                    cash_advance_id INTEGER NOT NULL,
                    repayment_date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    payroll_run_id INTEGER
                );
                CREATE TABLE payroll_runs (id INTEGER PRIMARY KEY, status TEXT);
                INSERT INTO payroll_runs VALUES (4,'Paid');
                INSERT INTO cash_advance_repayments VALUES
                    (15,12,'2026-07-02','Manual',1,NULL),
                    (29,12,'2026-08-03','Manual',1,NULL),
                    (30,12,'2026-08-15','Manual',1,NULL),
                    (42,12,'2026-09-18','Manual',1,NULL),
                    (43,12,'2026-09-18','Manual',1,NULL),
                    (44,12,'2026-09-19','Manual',1,NULL),
                    (45,12,'2026-09-20','Manual',1,NULL),
                    (46,12,'2026-09-21','Manual',1,NULL),
                    (47,12,'2026-09-22','Payroll',1,4),
                    (48,12,'2026-09-23','Manual',0,NULL);
            """)

    def _history(self):
        with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            return repayment_history(conn, 12)

    def test_no_outbox_table_returns_unavailable_not_missing(self):
        before = self.path.read_bytes()
        rows = self._history()
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(
            x["accounting_handoff_state"] == "outbox_status_unavailable"
            for x in rows if x["source"] == "Manual"
        ))
        self.assertIsNone(next(x for x in rows if x["source"] == "Payroll")["accounting_handoff_state"])
        self.assertEqual(before, self.path.read_bytes())

    def test_exact_staff_event_identity_and_status_no_financial_writes(self):
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE integration_outbox (
                    id INTEGER PRIMARY KEY,
                    destination TEXT, external_source TEXT,
                    event_type TEXT, external_id TEXT, status TEXT
                );
                INSERT INTO integration_outbox VALUES
                    (1,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:29','Pending'),
                    (2,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:30','Completed'),
                    (3,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:42','Retry'),
                    (4,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:43','Dead Letter'),
                    (5,'pos','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:15','Completed'),
                    (6,'accounting','another_app','cash_advance.repaid',
                     'cash-advance-repayment:15','Completed'),
                    (7,'accounting','hidden_oasis_staff_payroll','cash_advance.released',
                     'cash-advance-repayment:15','Completed'),
                    (8,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:44','Pending'),
                    (9,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:44','Completed'),
                    (10,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:45','Processing'),
                    (11,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:46',NULL),
                    (12,'accounting','hidden_oasis_staff_payroll','cash_advance.repaid',
                     'cash-advance-repayment:47','Completed');
            """)
        before = self.path.read_bytes()
        rows = {x["id"]: x for x in self._history()}
        self.assertEqual(rows[15]["accounting_handoff_state"], "missing_staff_outbox")
        self.assertIsNone(rows[15]["accounting_outbox_status"])
        self.assertEqual(rows[29]["accounting_handoff_state"], "pending_delivery")
        self.assertEqual(rows[30]["accounting_handoff_state"], "delivered_posting_unverified")
        self.assertEqual(rows[42]["accounting_handoff_state"], "delivery_requires_review")
        self.assertEqual(rows[43]["accounting_outbox_status"], "Dead Letter")
        self.assertEqual(rows[44]["accounting_handoff_state"], "delivered_posting_unverified")
        self.assertEqual(rows[44]["accounting_outbox_status"], "Completed")
        self.assertEqual(rows[45]["accounting_handoff_state"], "delivery_requires_review")
        self.assertEqual(rows[46]["accounting_handoff_state"], "delivery_requires_review")
        self.assertIsNone(rows[47]["accounting_handoff_state"])
        self.assertEqual(before, self.path.read_bytes())

    def test_partial_legacy_outbox_schema_is_reported_as_unavailable(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE integration_outbox (id INTEGER, status TEXT)")
        rows = self._history()
        self.assertEqual(rows[0]["accounting_handoff_state"], "outbox_status_unavailable")

    def test_ui_never_presents_completed_delivery_as_posted(self):
        page = Path("apps/web/app/cash-advances/page.tsx").read_text(encoding="utf-8")
        self.assertIn("accountingHandoffLabel", page)
        self.assertIn("missing_staff_outbox", page)
        self.assertIn("Delivered · posting unverified", page)
        self.assertIn("No Staff Accounting handoff", page)
        self.assertIn("a fully paid advance does not confirm cash posting", page)
        self.assertNotIn("Accounting posted", page)


if __name__ == "__main__":
    unittest.main()
