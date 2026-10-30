from __future__ import annotations

import sqlite3
import unittest
from datetime import date

from core.payroll_engine import PayrollResult
from core.payroll_statutory import apply_calendar_month_statutory
from core.statutory_legacy_history import legacy_paid_first_half_evidence
from core.statutory_snapshots import (
    assert_prior_month_statutory_coverage,
    ensure_statutory_snapshot_schema,
    previous_month_snapshot_totals,
    replace_run_employee_snapshots,
)


class LegacyOctoberPaidStatutoryTests(unittest.TestCase):
    """Legacy Paid Sep30-Oct14 has real withholding but no month snapshots."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE employees(id INTEGER PRIMARY KEY);
            INSERT INTO employees VALUES(1);
            CREATE TABLE app_settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE payroll_runs(
                id INTEGER PRIMARY KEY,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                status TEXT NOT NULL,
                superseded_by_run_id INTEGER
            );
            CREATE TABLE payroll_items(
                id INTEGER PRIMARY KEY,
                payroll_run_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL,
                gross_pay REAL NOT NULL,
                sss_ee REAL NOT NULL DEFAULT 0,
                philhealth_ee REAL NOT NULL DEFAULT 0,
                pagibig_ee REAL NOT NULL DEFAULT 0,
                sss_er REAL NOT NULL DEFAULT 0,
                sss_ec REAL NOT NULL DEFAULT 0,
                philhealth_er REAL NOT NULL DEFAULT 0,
                pagibig_er REAL NOT NULL DEFAULT 0
            );
            INSERT INTO payroll_runs VALUES(
                17,'2026-09-30','2026-10-14','Paid',NULL
            );
            INSERT INTO payroll_items VALUES(
                21,17,1,9500,500,125,100,900,30,125,100
            );
            INSERT INTO payroll_runs VALUES(
                18,'2026-10-15','2026-10-30','Draft',NULL
            );
            """
        )
        ensure_statutory_snapshot_schema(self.conn)
        self.month = date(2026, 10, 1)
        self.before = date(2026, 10, 15)

    def evidence(self):
        return legacy_paid_first_half_evidence(self.conn, 1, self.month, self.before)

    def totals(self):
        return previous_month_snapshot_totals(self.conn, 1, self.month, self.before)

    def test_paid_legacy_first_half_uses_recorded_withholding_without_writes(self):
        changes = self.conn.total_changes
        e = self.evidence()
        self.assertEqual(e["run_id"], 17)
        self.assertEqual(e["gross"], 9500)
        self.assertEqual(e["sss"], 500)
        self.assertEqual(e["philhealth"], 125)
        self.assertEqual(e["pagibig"], 100)
        self.assertEqual(e["sss_er"], 900)
        self.assertEqual(self.totals()["gross"], 9500)
        self.assertEqual(self.totals()["pagibig"], 100)
        self.assertEqual(self.conn.total_changes, changes)
        self.assertEqual(
            self.conn.execute("SELECT count(*) FROM payroll_statutory_months").fetchone()[0], 0
        )

    def test_october_second_half_deducts_only_the_remaining_monthly_shares(self):
        result = PayrollResult(
            employee_id=1,
            employee_code="TEST",
            full_name="Synthetic Employee",
            gross_pay=10000,
            warnings=[],
        )
        snap = apply_calendar_month_statutory(
            self.conn,
            result,
            {
                "id": 1,
                "declared_monthly_base": 10000,
                "benefits_sss": 1,
                "benefits_philhealth": 1,
                "benefits_pagibig": 1,
            },
            "2026-10-15",
            "2026-10-30",
            gross_by_month={self.month: 10000},
            get_sss_share=lambda conn, gross: (gross * .05, gross * .09, gross * .004),
        )
        self.assertEqual(result.pagibig_ee, 100)
        self.assertEqual(result.philhealth_ee, 125)
        self.assertEqual(result.pagibig_er, 100)
        self.assertEqual(result.philhealth_er, 125)
        self.assertEqual(result.sss_ee, 475)
        self.assertEqual(result.sss_er, 855)
        self.assertEqual(result.sss_ec, 48)
        self.assertEqual(snap[self.month]["pagibig_ee"], 100)
        self.assertTrue(any("earlier Paid first-half" in w for w in result.warnings))
        self.assertEqual(self.conn.execute("SELECT status FROM payroll_runs WHERE id=17").fetchone()[0], "Paid")

    def test_legacy_paid_withholding_satisfies_later_draft_coverage(self):
        self.assertIsNone(
            assert_prior_month_statutory_coverage(
                self.conn, 18, 1, "2026-10-15", "2026-10-30"
            )
        )

    def test_draft_is_not_a_withholding_source(self):
        self.conn.execute("UPDATE payroll_runs SET status='Draft' WHERE id=17")
        self.assertIsNone(self.evidence())
        self.assertEqual(self.totals()["pagibig"], 0)

    def test_approved_without_snapshots_is_not_taken_as_paid(self):
        self.conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=17")
        self.assertIsNone(self.evidence())
        self.assertEqual(self.totals()["pagibig"], 0)
        with self.assertRaisesRegex(ValueError, "lacks a statutory snapshot"):
            assert_prior_month_statutory_coverage(self.conn, 18, 1, "2026-10-15", "2026-10-30")

    def test_superseded_paid_run_is_not_counted_twice(self):
        self.conn.execute("UPDATE payroll_runs SET superseded_by_run_id=99 WHERE id=17")
        self.assertIsNone(self.evidence())
        self.assertEqual(self.totals()["sss"], 0)

    def test_partial_historical_month_snapshots_are_not_guessed(self):
        replace_run_employee_snapshots(
            self.conn,17,1,{date(2026, 9, 1): {"gross_pay": 100}}
        )
        self.assertIsNone(self.evidence())
        with self.assertRaisesRegex(ValueError, "lacks a statutory snapshot"):
            assert_prior_month_statutory_coverage(self.conn, 18, 1, "2026-10-15", "2026-10-30")

    def test_current_month_snapshot_is_used_without_legacy_fallback(self):
        replace_run_employee_snapshots(
            self.conn,17,1,{self.month: {
                "gross_pay": 9000,
                "sss_ee": 500,
                "philhealth_ee": 125,
                "pagibig_ee": 100,
            }}
        )
        self.assertIsNone(self.evidence())
        self.assertEqual(self.totals()["gross"],9000)
        self.assertEqual(self.totals()["sss"],500)
        self.assertEqual(self.totals()["pagibig"],100)

    def test_same_month_historical_missing_snapshot_still_blocks(self):
        self.conn.execute(
            "UPDATE payroll_runs SET period_start='2026-10-01' WHERE id=17"
        )
        self.assertIsNone(self.evidence())
        with self.assertRaisesRegex(ValueError,"lacks a statutory snapshot"):
            assert_prior_month_statutory_coverage(self.conn,18,1,"2026-10-15","2026-10-30")

    def test_unrelated_cutoff_cannot_be_mislabeled_first_half(self):
        self.conn.execute(
            "UPDATE payroll_runs SET period_end='2026-10-13' WHERE id=17"
        )
        self.assertIsNone(self.evidence())
        with self.assertRaisesRegex(ValueError,"lacks a statutory snapshot"):
            assert_prior_month_statutory_coverage(self.conn,18,1,"2026-10-15","2026-10-30")

    def test_evidence_is_not_available_before_earlier_payroll_ends(self):
        self.assertIsNone(legacy_paid_first_half_evidence(
            self.conn,1,self.month,date(2026,10,14)
        ))

    def test_duplicate_finalized_legacy_runs_fail_closed(self):
        self.conn.execute(
            "INSERT INTO payroll_runs VALUES(25,'2026-09-30','2026-10-14','Paid',NULL)"
        )
        self.conn.execute(
            "INSERT INTO payroll_items VALUES(26,25,1,9500,500,125,100,900,30,125,100)"
        )
        with self.assertRaisesRegex(ValueError,"Multiple finalized first-half payrolls"):
            self.evidence()

    def test_negative_legacy_statutory_amounts_are_rejected(self):
        self.conn.execute("UPDATE payroll_items SET pagibig_ee=-100 WHERE id=21")
        with self.assertRaisesRegex(ValueError,"Negative legacy statutory"):
            self.evidence()


if __name__ == "__main__":
    unittest.main()
