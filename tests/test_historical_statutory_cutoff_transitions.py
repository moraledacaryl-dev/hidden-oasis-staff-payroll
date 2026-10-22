from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.audit_historical_statutory_cutoff_transitions import (
    audit_historical_statutory_cutoff_transitions,
)


class HistoricalStatutoryCutoffTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "staff.sqlite"
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE payroll_runs(
                    id INTEGER PRIMARY KEY,
                    status TEXT, superseded_by_run_id INTEGER,
                    period_start TEXT, period_end TEXT
                );
                CREATE TABLE payroll_items(
                    id INTEGER PRIMARY KEY,
                    payroll_run_id INTEGER, employee_id INTEGER,
                    sss_ee REAL DEFAULT 0,sss_er REAL DEFAULT 0,sss_ec REAL DEFAULT 0,
                    philhealth_ee REAL DEFAULT 0,philhealth_er REAL DEFAULT 0,
                    pagibig_ee REAL DEFAULT 0,pagibig_er REAL DEFAULT 0
                );
                CREATE TABLE payroll_statutory_months(
                    id INTEGER PRIMARY KEY,payroll_run_id INTEGER,employee_id INTEGER
                );
                INSERT INTO payroll_runs VALUES
                    (11,'Paid',NULL,'2026-08-15','2026-08-30'),
                    (13,'Paid',NULL,'2026-08-31','2026-09-14'),
                    (14,'Paid',NULL,'2026-09-15','2026-09-29');
            """)
            # Only original source statutory contribution fields; no gross or PII.
            self.item(conn, 11, 1, ph=100, pi=50, sss=110)
            self.item(conn, 11, 2, ph=75, pi=0, sss=120)
            self.item(conn, 11, 3, ph=50, pi=0, sss=130)
            self.item(conn, 13, 1, ph=0, pi=0, sss=150)
            self.item(conn, 13, 2, ph=0, pi=0, sss=160)
            self.item(conn, 13, 3, ph=30, pi=0, sss=170)
            self.item(conn, 14, 1, ph=200, pi=100, sss=180)
            self.item(conn, 14, 2, ph=150, pi=0, sss=190)
            self.item(conn, 14, 3, ph=100, pi=0, sss=200)
            conn.commit()

    @staticmethod
    def item(conn: sqlite3.Connection, run_id: int, employee_id: int, *,
             ph: float, pi: float, sss: float) -> None:
        conn.execute(
            """INSERT INTO payroll_items(
                payroll_run_id,employee_id,sss_ee,sss_er,sss_ec,
                philhealth_ee,philhealth_er,pagibig_ee,pagibig_er
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (run_id, employee_id, sss, 2 * sss, 0, ph, ph, pi, pi),
        )

    def report(self, limit: int = 10) -> dict:
        with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            return audit_historical_statutory_cutoff_transitions(conn, limit)

    def test_september_pattern_counts_and_original_saved_money_only(self) -> None:
        before = self.path.read_bytes()
        out = self.report()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(out["read_only"])
        self.assertTrue(out["not_proof_of_duplicate_deduction"])
        self.assertEqual(out["cross_month_runs_examined"], 1)
        self.assertEqual(out["cross_month_following_pairs_examined"], 1)
        record = out["transition_review_sample"][0]
        self.assertEqual(record["cross_month_run_id"], 13)
        self.assertEqual(record["following_run_id"], 14)
        self.assertEqual(record["preceding_reference_run_id"], 11)
        self.assertEqual(record["matched_employee_count"], 3)
        self.assertEqual(record["matched_with_preceding_run_count"], 3)
        self.assertEqual(record["zero_in_cross_positive_in_follow_employee_counts"], {
            "philhealth": 2, "pagibig": 1,
        })
        self.assertEqual(record["follow_about_twice_prior_employee_counts"], {
            "philhealth": 3, "pagibig": 1,
        })
        self.assertEqual(record["zero_then_about_twice_prior_employee_counts"], {
            "philhealth": 2, "pagibig": 1,
        })
        self.assertEqual(record["cross_month_saved_by_program_php"]["sss"], 1440)
        self.assertEqual(record["following_saved_by_program_php"]["philhealth"], 900)
        self.assertNotIn("full_name", str(out))
        self.assertNotIn("payroll_gross", str(out))

    def test_approved_following_run_not_used_as_paid_evidence(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=14")
        out = self.report()
        self.assertEqual(out["cross_month_runs_without_following_match"], 1)
        self.assertEqual(out["cross_month_following_pairs_examined"], 0)
        self.assertEqual(
            out["transition_review_sample"][0]["status"],
            "no_following_paid_run_in_same_month",
        )

    def test_duplicate_following_start_date_is_ambiguous_not_arbitrary(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """INSERT INTO payroll_runs VALUES
                (15,'Paid',NULL,'2026-09-15','2026-09-29')"""
            )
            self.item(conn, 15, 1, ph=200, pi=100, sss=180)
        out = self.report()
        self.assertEqual(out["ambiguous_following_run_count"], 1)
        self.assertEqual(out["cross_month_following_pairs_examined"], 0)
        self.assertEqual(
            out["transition_review_sample"][0]["candidate_following_run_ids_sample"],
            [14, 15],
        )

    def test_superseded_following_run_is_excluded(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_runs SET superseded_by_run_id=99 WHERE id=14")
        out = self.report()
        self.assertEqual(out["cross_month_runs_without_following_match"], 1)
        self.assertEqual(out["cross_month_following_pairs_examined"], 0)

    def test_missing_prior_reference_does_not_infer_double_deductions(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=11")
        row = self.report()["transition_review_sample"][0]
        self.assertIsNone(row["preceding_reference_run_id"])
        self.assertEqual(row["matched_with_preceding_run_count"], 0)
        self.assertEqual(row["follow_about_twice_prior_employee_counts"], {
            "philhealth": 0, "pagibig": 0,
        })
        self.assertEqual(row["zero_in_cross_positive_in_follow_employee_counts"]["philhealth"], 2)

    def test_duplicate_employee_items_excluded_from_matching_but_kept_in_source_totals(self) -> None:
        with sqlite3.connect(self.path) as conn:
            self.item(conn, 14, 1, ph=200, pi=100, sss=180)
        row = self.report()["transition_review_sample"][0]
        self.assertEqual(row["duplicate_employee_item_ids_excluded_count"], 1)
        self.assertEqual(row["matched_employee_count"], 2)
        self.assertEqual(row["following_payroll_items"], 4)
        self.assertEqual(row["following_saved_by_program_php"]["philhealth"], 1300)

    def test_bounded_run_and_employee_samples(self) -> None:
        out = self.report(limit=0)
        self.assertEqual(out["cross_month_following_pairs_examined"], 1)
        self.assertEqual(out["transition_review_sample"], [])
        self.assertTrue(out["transition_review_sample_truncated"])
        row = self.report(limit=1)["transition_review_sample"][0]
        self.assertEqual(len(row["employee_id_pattern_sample"]), 1)
        self.assertTrue(row["employee_id_pattern_sample_truncated"])


if __name__ == "__main__":
    unittest.main()
