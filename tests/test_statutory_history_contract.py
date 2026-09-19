from __future__ import annotations

import sqlite3
import unittest
from datetime import date

from core.statutory_history import month_previous_contribs


class StatutoryHistoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE payroll_runs(
                id INTEGER PRIMARY KEY,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                status TEXT NOT NULL,
                superseded_by_run_id INTEGER
            );
            CREATE TABLE payroll_items(
                payroll_run_id INTEGER,
                employee_id INTEGER,
                gross_pay REAL DEFAULT 0,
                sss_ee REAL DEFAULT 0,
                philhealth_ee REAL DEFAULT 0,
                pagibig_ee REAL DEFAULT 0,
                sss_er REAL DEFAULT 0,
                sss_ec REAL DEFAULT 0,
                philhealth_er REAL DEFAULT 0,
                pagibig_er REAL DEFAULT 0
            );
            """
        )

    def _run(self, run_id: int, status: str, superseded_by: int | None, gross: float, sss: float) -> None:
        self.conn.execute(
            "INSERT INTO payroll_runs VALUES(?,?,?,?,?)",
            (run_id, "2026-06-01", "2026-06-15", status, superseded_by),
        )
        self.conn.execute(
            "INSERT INTO payroll_items(payroll_run_id,employee_id,gross_pay,sss_ee) VALUES(?,?,?,?)",
            (run_id, 3, gross, sss),
        )

    def test_replacement_does_not_double_count_superseded_original(self) -> None:
        self._run(4, "Paid", 5, 5000, 250)
        self._run(5, "Paid", None, 5200, 275)
        got = month_previous_contribs(self.conn, 3, date(2026, 6, 1), date(2026, 6, 16))
        self.assertEqual(got["gross"], 5200)
        self.assertEqual(got["sss"], 275)

    def test_draft_is_not_treated_as_withheld_history(self) -> None:
        self._run(12, "Draft", None, 7000, 350)
        got = month_previous_contribs(self.conn, 3, date(2026, 6, 1), date(2026, 6, 16))
        self.assertEqual(got["gross"], 0)
        self.assertEqual(got["sss"], 0)


if __name__ == "__main__":
    unittest.main()
