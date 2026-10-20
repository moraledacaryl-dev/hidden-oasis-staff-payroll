from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.audit_manual_repayment_outbox import audit_manual_repayment_outbox


class HistoricalManualRepaymentOutboxAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "staff.sqlite"
        with sqlite3.connect(self.path) as conn:
            conn.executescript(
                """
                CREATE TABLE cash_advance_repayments(
                    id INTEGER PRIMARY KEY,
                    cash_advance_id INTEGER,
                    repayment_date TEXT,
                    amount REAL,
                    source TEXT,
                    payment_method TEXT,
                    method TEXT,
                    reference TEXT,
                    active INTEGER
                );
                CREATE TABLE integration_outbox(
                    id INTEGER PRIMARY KEY,
                    destination TEXT,
                    event_type TEXT,
                    external_id TEXT,
                    status TEXT
                );

                INSERT INTO cash_advance_repayments VALUES
                    (1,50,'2026-09-05',125.25,'Manual','GCash','GCash','ref-a',1),
                    (2,50,'2026-09-06',75.10,'Manual','Cash','Cash','ref-b',1),
                    (3,50,'2026-09-07',60,'Manual','Cash','Cash','ref-c',1),
                    (4,50,'2026-09-08',30,'Payroll','Payroll deduction','Payroll deduction',NULL,1),
                    (5,60,'2026-09-10',40,'Manual','Cash','Cash','reversed',0),
                    (6,70,'2026-09-11',20,'Manual','Bank transfer','Bank transfer','ref-d',1),
                    (7,70,'2026-09-11',20,'Manual','Bank transfer','Bank transfer','ref-d',1),
                    (8,70,'2026-09-12',5,'Manual','Cash','Cash',NULL,1);

                INSERT INTO integration_outbox VALUES
                    (20,'accounting','cash_advance.repaid','cash-advance-repayment:2','Completed'),
                    (21,'accounting','cash_advance.repaid','cash-advance-repayment:3','Dead Letter'),
                    (22,'operations','cash_advance.repaid','cash-advance-repayment:1','Completed'),
                    (23,'accounting','cash_advance.released','cash-advance-repayment:8','Completed');
                """
            )

    def test_classifies_missing_dead_letter_and_delivered_only(self) -> None:
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            result = audit_manual_repayment_outbox(conn)
        self.assertTrue(result["read_only"])
        self.assertEqual(result["manual_repayment_count"], 6)
        self.assertEqual(result["manual_repayment_amount_php"], 305.35)
        self.assertEqual(result["missing_staff_outbox_count"], 4)
        self.assertEqual(result["missing_staff_outbox_amount_php"], 170.25)
        self.assertEqual(result["outbox_not_completed_count"], 1)
        self.assertEqual(result["outbox_not_completed_amount_php"], 60.0)
        self.assertEqual(result["delivered_not_necessarily_posted_count"], 1)
        self.assertEqual(result["review_candidate_count"], 5)
        self.assertEqual([row["repayment_id"] for row in result["review_candidate_sample"]], [1,3,6,7,8])
        self.assertEqual(result["possible_duplicate_groups_count"], 1)
        self.assertEqual(result["possible_duplicate_groups_sample"][0]["repayment_ids"], [6,7])

    def test_read_only_connection_does_not_change_database(self) -> None:
        before = self.path.read_bytes()
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            audit_manual_repayment_outbox(conn)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM cash_advance_repayments")
        self.assertEqual(self.path.read_bytes(), before)

    def test_summary_limit_does_not_hide_totals(self) -> None:
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            result = audit_manual_repayment_outbox(conn, sample_limit=0)
        self.assertEqual(result["review_candidate_sample"], [])
        self.assertTrue(result["review_candidate_sample_truncated"])
        self.assertEqual(result["review_candidate_count"], 5)
        self.assertEqual(result["possible_duplicate_groups_count"], 1)

    def test_missing_schema_fails_closed(self) -> None:
        with sqlite3.connect(":memory:") as conn:
            with self.assertRaisesRegex(RuntimeError, "Missing columns"):
                audit_manual_repayment_outbox(conn)

    def test_missing_outbox_table_fails_closed(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE integration_outbox")
            conn.commit()
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            with self.assertRaisesRegex(RuntimeError, "Missing columns in integration_outbox"):
                audit_manual_repayment_outbox(conn)


if __name__ == "__main__":
    unittest.main()
