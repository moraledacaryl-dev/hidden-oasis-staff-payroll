from __future__ import annotations

import sqlite3
import unittest

from core.payroll_engine import (
    compute_13th_month_basis,
    create_accounting_queue_for_13th_month,
    save_13th_month_run,
)


class ThirteenthMonthMoneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript(
            """
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                full_name TEXT
            );

            CREATE TABLE payroll_runs (
                id INTEGER PRIMARY KEY,
                period_start TEXT,
                status TEXT
            );

            CREATE TABLE payroll_items (
                id INTEGER PRIMARY KEY,
                payroll_run_id INTEGER,
                employee_id INTEGER,
                regular_pay REAL,
                paid_leave_pay REAL
            );

            CREATE TABLE payroll_13th_month_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                year INTEGER,
                period_label TEXT,
                basis_amount REAL,
                base_13th_amount REAL,
                adjustment_amount REAL,
                deductions REAL,
                net_13th_pay REAL,
                status TEXT,
                release_date TEXT,
                prepared_by TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(employee_id, year, period_label)
            );

            CREATE TABLE payroll_13th_month_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                kind TEXT,
                label TEXT,
                amount REAL,
                notes TEXT,
                sort_order INTEGER
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

            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT,
                action TEXT,
                table_name TEXT,
                record_id INTEGER,
                details TEXT,
                created_at TEXT
            );
            """
        )

        self.conn.execute(
            "INSERT INTO employees(id, full_name) VALUES(1, 'Test Employee')"
        )

        self.conn.execute(
            """
            INSERT INTO payroll_runs(id, period_start, status)
            VALUES(1, '2026-01-01', 'Paid')
            """
        )

        self.conn.execute(
            """
            INSERT INTO payroll_items(
                id,
                payroll_run_id,
                employee_id,
                regular_pay,
                paid_leave_pay
            )
            VALUES(1, 1, 1, 1000.005, 200.005)
            """
        )

        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_basis_and_saved_run_use_half_up_centavos(self) -> None:
        basis = compute_13th_month_basis(
            self.conn,
            employee_id=1,
            year=2026,
        )

        self.assertEqual(basis, 1200.01)

        run_id = save_13th_month_run(
            self.conn,
            employee_id=1,
            year=2026,
            period_label="2026 Annual",
            basis_amount=basis,
            adjustment_amount=10.005,
            deductions=5.005,
            status="Approved",
            release_date="2026-12-15",
            prepared_by="Owner",
            notes="Centavo test",
        )

        run = self.conn.execute(
            """
            SELECT *
            FROM payroll_13th_month_runs
            WHERE id=?
            """,
            (run_id,),
        ).fetchone()

        self.assertEqual(float(run["basis_amount"]), 1200.01)
        self.assertEqual(float(run["base_13th_amount"]), 100.00)
        self.assertEqual(float(run["adjustment_amount"]), 10.01)
        self.assertEqual(float(run["deductions"]), 5.01)
        self.assertEqual(float(run["net_13th_pay"]), 105.00)

        lines = {
            row["label"]: float(row["amount"])
            for row in self.conn.execute(
                """
                SELECT label, amount
                FROM payroll_13th_month_lines
                WHERE run_id=?
                """,
                (run_id,),
            ).fetchall()
        }

        self.assertEqual(lines["13th month basis"], 1200.01)
        self.assertEqual(lines["Base 13th month pay"], 100.00)
        self.assertEqual(lines["Manual adjustment"], 10.01)
        self.assertEqual(lines["Deductions"], 5.01)

    def test_accounting_export_matches_saved_net_to_centavo(self) -> None:
        run_id = save_13th_month_run(
            self.conn,
            employee_id=1,
            year=2026,
            period_label="2026 Annual",
            basis_amount=1200.01,
            adjustment_amount=10.005,
            deductions=5.005,
            status="Paid",
            release_date="2026-12-15",
            prepared_by="Owner",
            notes="Accounting test",
        )

        create_accounting_queue_for_13th_month(
            self.conn,
            run_id,
        )

        run = self.conn.execute(
            """
            SELECT net_13th_pay
            FROM payroll_13th_month_runs
            WHERE id=?
            """,
            (run_id,),
        ).fetchone()

        queued = self.conn.execute(
            """
            SELECT amount
            FROM accounting_export_queue
            WHERE source_type='13th Month'
              AND source_id=?
            """,
            (run_id,),
        ).fetchone()

        self.assertIsNotNone(queued)
        self.assertEqual(
            float(queued["amount"]),
            float(run["net_13th_pay"]),
        )


if __name__ == "__main__":
    unittest.main()
