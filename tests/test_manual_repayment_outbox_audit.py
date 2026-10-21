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
                    external_source TEXT,
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
                    (20,'accounting','cash_advance.repaid','hidden_oasis_staff_payroll','cash-advance-repayment:2','Completed'),
                    (21,'accounting','cash_advance.repaid','hidden_oasis_staff_payroll','cash-advance-repayment:3','Dead Letter'),
                    (22,'operations','cash_advance.repaid','hidden_oasis_staff_payroll','cash-advance-repayment:1','Completed'),
                    (23,'accounting','cash_advance.released','hidden_oasis_staff_payroll','cash-advance-repayment:8','Completed'),
                    (24,'accounting','cash_advance.repaid','a_different_app','cash-advance-repayment:7','Completed');
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
        self.assertEqual(result["outbox_not_completed_by_status"], {
            "Dead Letter": {"count": 1, "amount_php": 60.0},
        })
        self.assertEqual(result["outbox_not_completed_amount_php"], 60.0)
        self.assertEqual(result["delivered_not_necessarily_posted_count"], 1)
        self.assertEqual(result["review_candidate_count"], 5)
        self.assertEqual([row["repayment_id"] for row in result["review_candidate_sample"]], [1,3,6,7,8])
        self.assertEqual(result["possible_duplicate_groups_count"], 1)
        self.assertEqual(result["possible_duplicate_groups_sample"][0]["repayment_ids"], [6,7])

    def test_status_breakdown_distinguishes_retry_from_dead_letter(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO integration_outbox VALUES (25, ?, ?, ?, ?, ?)",
                         ("accounting", "cash_advance.repaid",
                          "hidden_oasis_staff_payroll", "cash-advance-repayment:1", "Retry"))
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            result = audit_manual_repayment_outbox(conn, sample_limit=0)
        self.assertEqual(result["outbox_not_completed_count"], 2)
        self.assertEqual(result["outbox_not_completed_amount_php"], 185.25)
        self.assertEqual(result["outbox_not_completed_by_status"], {
            "Dead Letter": {"count": 1, "amount_php": 60.0},
            "Retry": {"count": 1, "amount_php": 125.25},
        })
        self.assertEqual(result["missing_staff_outbox_count"], 3)
        self.assertEqual(result["review_candidate_count"], 5)
        self.assertEqual(result["review_candidate_sample"], [])

    def test_manual_method_review_flags_completed_events_and_ambiguous_methods(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                "INSERT INTO cash_advance_repayments VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (9,80,"2026-09-13",12.50,"Manual","Payroll deduction",
                     "Payroll deduction","sensitive-ref",1),
                    (10,80,"2026-09-14",7.25,"Manual","Other","Other",None,1),
                    (11,80,"2026-09-15",8.15,"Manual",None,None,None,1),
                ],
            )
            conn.execute(
                "INSERT INTO integration_outbox VALUES (?,?,?,?,?,?)",
                (26,"accounting","cash_advance.repaid","hidden_oasis_staff_payroll",
                 "cash-advance-repayment:9","Completed"),
            )
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            result = audit_manual_repayment_outbox(conn, sample_limit=100)
        self.assertEqual(result["manual_repayment_count"], 9)
        self.assertEqual(result["payment_method_review_count"], 3)
        self.assertEqual(result["payment_method_review_amount_php"], 27.90)
        self.assertEqual(result["payment_method_review_by_reason"], {
            "manual_record_with_payroll_deduction_method": {
                "count": 1, "amount_php": 12.50,
            },
            "missing_receipt_method": {"count": 1, "amount_php": 8.15},
            "unverified_receipt_method": {"count": 1, "amount_php": 7.25},
        })
        sample = result["payment_method_review_sample"]
        self.assertEqual([row["repayment_id"] for row in sample], [9, 10, 11])
        self.assertEqual(sample[0]["classification"], "delivered_not_necessarily_posted")
        self.assertEqual(sample[0]["outbox_status"], "Completed")
        self.assertNotIn("sensitive-ref", str(sample))
        self.assertTrue(sample[0]["has_receipt_reference"])

    def test_method_review_zero_limit_preserves_count_and_truncation(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO cash_advance_repayments VALUES (?,?,?,?,?,?,?,?,?)",
                (9,80,"2026-09-13",10,"Manual","Other","Other",None,1),
            )
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            report = audit_manual_repayment_outbox(conn, sample_limit=0)
        self.assertEqual(report["payment_method_review_count"], 1)
        self.assertEqual(report["payment_method_review_amount_php"], 10.0)
        self.assertEqual(report["payment_method_review_sample"], [])
        self.assertTrue(report["payment_method_review_sample_truncated"])

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
