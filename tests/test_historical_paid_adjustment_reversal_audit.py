from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.audit_paid_adjustment_reversals import audit_paid_adjustment_reversals


class HistoricalPaidAdjustmentReversalAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "payroll.sqlite"
        with sqlite3.connect(self.path) as conn:
            conn.executescript(
                """
                CREATE TABLE payroll_runs (
                    id INTEGER PRIMARY KEY,
                    status TEXT,
                    paid_at TEXT,
                    revision_of_run_id INTEGER,
                    revision_treatment TEXT
                );
                CREATE TABLE cash_advance_repayments (
                    id INTEGER PRIMARY KEY,
                    cash_advance_id INTEGER,
                    payroll_run_id INTEGER,
                    amount REAL,
                    active INTEGER,
                    reversal_reason TEXT,
                    reversed_at TEXT
                );
                INSERT INTO payroll_runs(id,status,paid_at,revision_of_run_id,revision_treatment)
                VALUES
                    (10,'Paid','2026-09-30',NULL,NULL),
                    (11,'Paid','2026-10-10',10,'adjust_paid'),
                    (12,'Paid','2026-09-30',NULL,NULL),
                    (13,'Draft',NULL,12,'adjust_paid'),
                    (14,'Paid','2026-10-10',12,'adjust_paid');
                INSERT INTO cash_advance_repayments(
                    id,cash_advance_id,payroll_run_id,amount,active,reversal_reason,reversed_at
                ) VALUES
                    (1,50,10,200,0,'Superseded by paid payroll revision #11','2026-10-10'),
                    (2,51,10,100,1,NULL,NULL),
                    (3,52,12,30,0,'Manual correction','2026-10-10'),
                    (4,53,12,40,0,'Superseded by paid payroll revision #13','2026-10-10'),
                    (5,54,12,50,0,'Superseded by paid payroll revision #14','2026-10-10');
                """
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_report_only_flags_reversals_by_paid_adjustment(self) -> None:
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            report = audit_paid_adjustment_reversals(conn)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["finding_count"], 2)
        self.assertEqual(report["potentially_reversed_amount_php"], 250.0)
        self.assertEqual(
            [r["repayment_id"] for r in report["findings"]], [1, 5],
        )
        self.assertEqual(
            [r["revision_run_id"] for r in report["findings"]], [11, 14],
        )

    def test_read_only_database_remains_unchanged(self) -> None:
        before = self.path.read_bytes()
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as conn:
            audit_paid_adjustment_reversals(conn)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_schema_fails_instead_of_claiming_zero_findings(self) -> None:
        with sqlite3.connect(":memory:") as conn:
            with self.assertRaisesRegex(RuntimeError, "Missing columns"):
                audit_paid_adjustment_reversals(conn)


if __name__ == "__main__":
    unittest.main()
