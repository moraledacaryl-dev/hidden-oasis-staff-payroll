from __future__ import annotations

import sqlite3
import unittest
from datetime import date

from core.statutory_snapshots import (
    ensure_statutory_snapshot_schema,
    previous_month_snapshot_totals,
    replace_run_employee_snapshots,
)


class StatutorySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE employees(id INTEGER PRIMARY KEY);
            INSERT INTO employees VALUES(3);
            CREATE TABLE payroll_runs(
                id INTEGER PRIMARY KEY,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                status TEXT NOT NULL,
                superseded_by_run_id INTEGER
            );
            """
        )
        ensure_statutory_snapshot_schema(self.conn)

    def test_aug31_sep14_snapshot_is_visible_to_sep30_oct14(self) -> None:
        self.conn.execute("INSERT INTO payroll_runs VALUES(12,'2026-08-31','2026-09-14','Paid',NULL)")
        replace_run_employee_snapshots(
            self.conn,
            12,
            3,
            {
                date(2026, 8, 1): {"gross_pay": 500, "sss_ee": 25},
                date(2026, 9, 1): {"gross_pay": 6500, "sss_ee": 300, "philhealth_ee": 125, "pagibig_ee": 100},
            },
        )
        got = previous_month_snapshot_totals(self.conn, 3, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(got["gross"], 6500)
        self.assertEqual(got["sss"], 300)
        self.assertEqual(got["philhealth"], 125)
        self.assertEqual(got["pagibig"], 100)

    def test_superseded_and_draft_snapshots_are_excluded(self) -> None:
        self.conn.execute("INSERT INTO payroll_runs VALUES(4,'2026-09-01','2026-09-14','Paid',5)")
        self.conn.execute("INSERT INTO payroll_runs VALUES(5,'2026-09-01','2026-09-14','Paid',NULL)")
        self.conn.execute("INSERT INTO payroll_runs VALUES(6,'2026-09-15','2026-09-20','Draft',NULL)")
        replace_run_employee_snapshots(self.conn, 4, 3, {date(2026, 9, 1): {"gross_pay": 4000}})
        replace_run_employee_snapshots(self.conn, 5, 3, {date(2026, 9, 1): {"gross_pay": 5200}})
        replace_run_employee_snapshots(self.conn, 6, 3, {date(2026, 9, 1): {"gross_pay": 9999}})
        got = previous_month_snapshot_totals(self.conn, 3, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(got["gross"], 5200)


if __name__ == "__main__":
    unittest.main()
