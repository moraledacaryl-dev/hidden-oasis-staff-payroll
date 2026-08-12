from __future__ import annotations

import sqlite3
import unittest

from core.payroll_engine import (
    apply_cash_advance_repayments,
    reverse_cash_advance_repayments,
)


class CashAdvanceMoneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript(
            """
            CREATE TABLE payroll_runs (
                id INTEGER PRIMARY KEY,
                payout_date TEXT
            );

            CREATE TABLE payroll_items (
                id INTEGER PRIMARY KEY,
                payroll_run_id INTEGER,
                employee_id INTEGER,
                cash_advance_deduction REAL
            );

            CREATE TABLE cash_advances (
                id INTEGER PRIMARY KEY,
                employee_id INTEGER,
                amount REAL,
                outstanding_balance REAL,
                status TEXT,
                request_date TEXT
            );

            CREATE TABLE cash_advance_repayments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cash_advance_id INTEGER,
                payroll_run_id INTEGER,
                payment_date TEXT,
                amount REAL,
                method TEXT,
                notes TEXT,
                created_at TEXT
            );
            """
        )

        self.conn.execute(
            """
            INSERT INTO payroll_runs(id, payout_date)
            VALUES(1, '2026-08-15')
            """
        )

        self.conn.execute(
            """
            INSERT INTO payroll_items(
                id,
                payroll_run_id,
                employee_id,
                cash_advance_deduction
            )
            VALUES(1, 1, 7, 33.335)
            """
        )

        self.conn.execute(
            """
            INSERT INTO cash_advances(
                id,
                employee_id,
                amount,
                outstanding_balance,
                status,
                request_date
            )
            VALUES(
                10,
                7,
                100.00,
                100.00,
                'Released',
                '2026-08-01'
            )
            """
        )

        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_repayment_and_reverse_conserve_balance_to_centavo(self) -> None:
        apply_cash_advance_repayments(self.conn, 1)

        repayment = self.conn.execute(
            """
            SELECT amount
            FROM cash_advance_repayments
            WHERE payroll_run_id=1
            """
        ).fetchone()

        advance = self.conn.execute(
            """
            SELECT outstanding_balance, status
            FROM cash_advances
            WHERE id=10
            """
        ).fetchone()

        self.assertEqual(float(repayment["amount"]), 33.34)
        self.assertEqual(float(advance["outstanding_balance"]), 66.66)
        self.assertEqual(advance["status"], "Partially Paid")

        reverse_cash_advance_repayments(self.conn, 1)

        restored = self.conn.execute(
            """
            SELECT outstanding_balance, status
            FROM cash_advances
            WHERE id=10
            """
        ).fetchone()

        self.assertEqual(float(restored["outstanding_balance"]), 100.00)
        self.assertEqual(restored["status"], "Released")

        count = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM cash_advance_repayments
            WHERE payroll_run_id=1
            """
        ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_repayment_application_is_idempotent(self) -> None:
        apply_cash_advance_repayments(self.conn, 1)
        apply_cash_advance_repayments(self.conn, 1)

        count = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM cash_advance_repayments
            WHERE payroll_run_id=1
            """
        ).fetchone()[0]

        self.assertEqual(count, 1)

        balance = self.conn.execute(
            """
            SELECT outstanding_balance
            FROM cash_advances
            WHERE id=10
            """
        ).fetchone()[0]

        self.assertEqual(float(balance), 66.66)


if __name__ == "__main__":
    unittest.main()
