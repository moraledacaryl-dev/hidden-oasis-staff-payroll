from __future__ import annotations

import inspect
import sqlite3
import unittest

import api.schedule_publication as schedule_publication
import api.server as server
import api.staff_published_portal as staff_published_portal
from api.cash_advance_service import calculate_balance, recalculate_balance


class PublishedSelfServiceReadOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE cash_advances (
                id INTEGER PRIMARY KEY,
                amount REAL NOT NULL,
                remaining_balance REAL NOT NULL,
                outstanding_balance REAL NOT NULL,
                ledger_opening_balance REAL,
                status TEXT,
                repayment_per_cutoff REAL NOT NULL DEFAULT 0,
                deduction_per_payroll REAL NOT NULL DEFAULT 0,
                updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE cash_advance_repayments (
                id INTEGER PRIMARY KEY,
                cash_advance_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                source TEXT NOT NULL,
                payroll_run_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self.conn.execute(
            "CREATE TABLE payroll_runs (id INTEGER PRIMARY KEY, status TEXT)"
        )
        self.conn.execute(
            """
            INSERT INTO cash_advances(
                id, amount, remaining_balance, outstanding_balance,
                ledger_opening_balance, status, deduction_per_payroll, updated_at
            ) VALUES (1, 500, 500, 500, 500, 'Active', 100, 'sentinel')
            """
        )
        self.conn.execute(
            """
            INSERT INTO cash_advance_repayments(
                id, cash_advance_id, amount, source, active
            ) VALUES (1, 1, 125, 'Manual', 1)
            """
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_calculate_balance_is_pure(self) -> None:
        summary = calculate_balance(self.conn, 1)
        self.assertEqual(summary["balance"], 375.0)
        self.assertEqual(summary["status"], "Partially Paid")

        row = self.conn.execute(
            "SELECT remaining_balance, outstanding_balance, status, updated_at FROM cash_advances WHERE id=1"
        ).fetchone()
        self.assertEqual(float(row["remaining_balance"]), 500.0)
        self.assertEqual(float(row["outstanding_balance"]), 500.0)
        self.assertEqual(row["status"], "Active")
        self.assertEqual(row["updated_at"], "sentinel")

    def test_recalculate_balance_remains_explicit_persistence_path(self) -> None:
        summary = recalculate_balance(self.conn, 1)
        self.conn.commit()
        self.assertEqual(summary["balance"], 375.0)

        row = self.conn.execute(
            "SELECT remaining_balance, outstanding_balance, status, updated_at FROM cash_advances WHERE id=1"
        ).fetchone()
        self.assertEqual(float(row["remaining_balance"]), 375.0)
        self.assertEqual(float(row["outstanding_balance"]), 375.0)
        self.assertEqual(row["status"], "Partially Paid")
        self.assertNotEqual(row["updated_at"], "sentinel")

    def test_published_portal_get_does_not_use_persistent_recalculation_or_commit(self) -> None:
        source = inspect.getsource(staff_published_portal.published_self_service)
        self.assertIn("calculate_balance", source)
        self.assertNotIn("recalculate_balance", source)
        self.assertNotIn("conn.commit", source)
        self.assertNotIn("ensure_hr_schema", source)
        self.assertNotIn("ensure_publication_schema", source)
        self.assertNotIn("ensure_cash_schema", source)

    def test_publication_get_is_schema_side_effect_free(self) -> None:
        source = inspect.getsource(schedule_publication.get_schedule_publication)
        self.assertNotIn("ensure_schema", source)
        self.assertNotIn("conn.commit", source)

    def test_publication_schema_is_initialized_at_startup(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_publication_schema(conn)", source)


if __name__ == "__main__":
    unittest.main()
