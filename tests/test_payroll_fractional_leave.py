from __future__ import annotations

import sqlite3
import unittest
from types import SimpleNamespace

from core.payroll_fractional_leave import apply_fractional_paid_leave_adjustment


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        INSERT INTO app_settings(key, value, updated_at) VALUES('standard_daily_paid_hours', '8', '2026-01-01');

        CREATE TABLE employees(
            id INTEGER PRIMARY KEY,
            employee_code TEXT,
            full_name TEXT,
            hourly_rate REAL,
            declared_monthly_base REAL DEFAULT 0,
            benefits_sss INTEGER DEFAULT 0,
            benefits_philhealth INTEGER DEFAULT 0,
            benefits_pagibig INTEGER DEFAULT 0,
            benefits_tax INTEGER DEFAULT 0
        );
        INSERT INTO employees(id, employee_code, full_name, hourly_rate) VALUES(1, 'E001', 'Test Employee', 100);

        CREATE TABLE leave_types(id INTEGER PRIMARY KEY, name TEXT, paid INTEGER);
        INSERT INTO leave_types(id, name, paid) VALUES(1, 'Vacation Leave', 1);

        CREATE TABLE leave_requests(
            id INTEGER PRIMARY KEY,
            employee_id INTEGER,
            leave_type_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            days REAL,
            paid INTEGER,
            status TEXT
        );
        INSERT INTO leave_requests(id, employee_id, leave_type_id, start_date, end_date, days, paid, status)
        VALUES(1, 1, 1, '2026-07-01', '2026-07-01', 0.5, 1, 'Approved');

        CREATE TABLE employee_leave_entitlements(
            employee_id INTEGER,
            leave_type_id INTEGER,
            year INTEGER,
            entitled INTEGER,
            used REAL,
            credits REAL
        );
        INSERT INTO employee_leave_entitlements(employee_id, leave_type_id, year, entitled, used, credits)
        VALUES(1, 1, 2026, 1, 0.5, 5);

        CREATE TABLE payroll_runs(id INTEGER PRIMARY KEY, period_start TEXT, period_end TEXT, status TEXT);
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
        CREATE TABLE sss_contribution_table(
            min_comp REAL,
            max_comp REAL,
            ee_share REAL,
            er_share REAL,
            ec_share REAL,
            active INTEGER
        );
        CREATE TABLE cash_advances(
            id INTEGER PRIMARY KEY,
            employee_id INTEGER,
            outstanding_balance REAL,
            status TEXT,
            request_date TEXT,
            custom_next_deduction REAL,
            repayment_per_cutoff REAL
        );
        """
    )
    return conn


class PayrollFractionalLeaveAdjustmentTests(unittest.TestCase):
    def test_fractional_paid_leave_updates_days_pay_gross_and_net(self):
        conn = make_conn()
        result = SimpleNamespace(
            employee_id=1,
            paid_leave_days=1.0,
            paid_leave_pay=800.0,
            regular_pay=0.0,
            ot_pay=0.0,
            night_diff_pay=0.0,
            holiday_pay=0.0,
            freelance_pay=0.0,
            other_earnings=0.0,
            other_deductions=0.0,
            gross_pay=800.0,
            sss_ee=0.0,
            philhealth_ee=0.0,
            pagibig_ee=0.0,
            sss_er=0.0,
            sss_ec=0.0,
            philhealth_er=0.0,
            pagibig_er=0.0,
            tax=0.0,
            cash_advance_deduction=0.0,
            total_deductions=0.0,
            net_pay=800.0,
            warnings=[],
        )

        adjusted = apply_fractional_paid_leave_adjustment(conn, result, '2026-07-01', '2026-07-15')

        self.assertEqual(adjusted.paid_leave_days, 0.5)
        self.assertEqual(adjusted.paid_leave_pay, 400.0)
        self.assertEqual(adjusted.gross_pay, 400.0)
        self.assertEqual(adjusted.net_pay, 400.0)
        self.assertTrue(any('prorated from 1 to 0.5' in warning for warning in adjusted.warnings))


if __name__ == "__main__":
    unittest.main()
