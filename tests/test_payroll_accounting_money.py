from __future__ import annotations

import sqlite3
import unittest

from core.payroll_engine import create_accounting_queue_for_payroll


class PayrollAccountingMoneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript(
            """
            CREATE TABLE payroll_runs (
                id INTEGER PRIMARY KEY,
                period_start TEXT,
                period_end TEXT,
                payout_date TEXT,
                run_label TEXT
            );

            CREATE TABLE payroll_items (
                id INTEGER PRIMARY KEY,
                payroll_run_id INTEGER,
                gross_pay REAL,
                net_pay REAL,
                sss_ee REAL,
                philhealth_ee REAL,
                pagibig_ee REAL,
                tax REAL,
                sss_er REAL,
                sss_ec REAL,
                philhealth_er REAL,
                pagibig_er REAL,
                cash_advance_deduction REAL
            );

            CREATE TABLE accounting_export_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT,
                source_id INTEGER,
                entry_date TEXT,
                description TEXT,
                debit_account TEXT,
                credit_account TEXT,
                amount REAL,
                status TEXT,
                created_at TEXT
            );

            CREATE TABLE app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )

        self.conn.execute(
            """
            INSERT INTO payroll_runs(
                id,
                period_start,
                period_end,
                payout_date,
                run_label
            )
            VALUES(
                1,
                '2026-08-01',
                '2026-08-14',
                '2026-08-15',
                'First Half'
            )
            """
        )

        self.conn.execute(
            """
            INSERT INTO payroll_items(
                id,
                payroll_run_id,
                gross_pay,
                net_pay,
                sss_ee,
                philhealth_ee,
                pagibig_ee,
                tax,
                sss_er,
                sss_ec,
                philhealth_er,
                pagibig_er,
                cash_advance_deduction
            )
            VALUES(
                1,
                1,
                1000.005,
                800.005,
                50.005,
                30.005,
                20.005,
                40.005,
                60.005,
                10.005,
                30.005,
                20.005,
                50.005
            )
            """
        )

        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_accounting_queue_uses_half_up_centavos(self) -> None:
        create_accounting_queue_for_payroll(self.conn, 1)

        rows = self.conn.execute(
            """
            SELECT description, amount
            FROM accounting_export_queue
            WHERE source_type='Payroll Run'
              AND source_id=1
            ORDER BY id
            """
        ).fetchall()

        amounts = {
            row["description"]: float(row["amount"])
            for row in rows
        }

        self.assertIn(
            "Payroll 2026-08-01 to 2026-08-14 (First Half) - gross payroll",
            amounts,
        )

        self.assertEqual(
            amounts[
                "Payroll 2026-08-01 to 2026-08-14 (First Half) - gross payroll"
            ],
            1000.01,
        )

        self.assertEqual(
            amounts[
                "Payroll 2026-08-01 to 2026-08-14 (First Half) - net pay release"
            ],
            800.01,
        )

        self.assertEqual(
            amounts[
                "Payroll 2026-08-01 to 2026-08-14 (First Half) - employee SSS"
            ],
            50.01,
        )

        # Employer SSS + EC is summed first, then rounded once.
        self.assertEqual(
            amounts[
                "Payroll 2026-08-01 to 2026-08-14 (First Half) - employer SSS/EC"
            ],
            70.01,
        )

    def test_accounting_queue_is_idempotent(self) -> None:
        create_accounting_queue_for_payroll(self.conn, 1)
        create_accounting_queue_for_payroll(self.conn, 1)

        count = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM accounting_export_queue
            WHERE source_type='Payroll Run'
              AND source_id=1
            """
        ).fetchone()[0]

        self.assertEqual(count, 10)


if __name__ == "__main__":
    unittest.main()
