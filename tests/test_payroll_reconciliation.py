from __future__ import annotations

import sqlite3
import unittest

from core.money import money
from core.payroll_engine import PayrollResult, add_payroll_lines


class PayrollReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript(
            """
            CREATE TABLE payroll_item_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payroll_item_id INTEGER,
                kind TEXT,
                label TEXT,
                amount REAL,
                hours REAL,
                days REAL,
                quantity REAL,
                notes TEXT,
                sort_order INTEGER
            );
            """
        )

    def tearDown(self) -> None:
        self.conn.close()

    def build_result(self) -> PayrollResult:
        result = PayrollResult(
            employee_id=1,
            employee_code="EMP-001",
            full_name="Test Employee",
        )

        result.regular_pay = 5000.01
        result.holiday_pay = 250.02
        result.ot_pay = 400.03
        result.night_diff_pay = 100.04
        result.paid_leave_pay = 300.05
        result.freelance_pay = 200.06
        result.other_earnings = 50.07

        result.sss_ee = 225.01
        result.philhealth_ee = 125.02
        result.pagibig_ee = 100.03
        result.tax = 75.04
        result.cash_advance_deduction = 300.05
        result.other_deductions = 25.06

        result.sss_er = 450.01
        result.sss_ec = 30.02
        result.philhealth_er = 125.02
        result.pagibig_er = 100.03

        result.gross_pay = money(
            result.regular_pay
            + result.holiday_pay
            + result.ot_pay
            + result.night_diff_pay
            + result.paid_leave_pay
            + result.freelance_pay
            + result.other_earnings
        )

        result.total_deductions = money(
            result.sss_ee
            + result.philhealth_ee
            + result.pagibig_ee
            + result.tax
            + result.cash_advance_deduction
            + result.other_deductions
        )

        result.net_pay = money(
            result.gross_pay - result.total_deductions
        )

        return result

    def test_gross_equals_sum_of_employee_earning_lines(self) -> None:
        result = self.build_result()

        add_payroll_lines(self.conn, 1, result)

        total = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payroll_item_lines
            WHERE payroll_item_id=1
              AND kind='earning'
            """
        ).fetchone()[0]

        self.assertEqual(
            money(total),
            result.gross_pay,
        )

    def test_total_deductions_equals_sum_of_employee_deduction_lines(self) -> None:
        result = self.build_result()

        add_payroll_lines(self.conn, 1, result)

        total = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payroll_item_lines
            WHERE payroll_item_id=1
              AND kind='deduction'
            """
        ).fetchone()[0]

        self.assertEqual(
            money(total),
            result.total_deductions,
        )

    def test_net_pay_equals_gross_less_deductions(self) -> None:
        result = self.build_result()

        self.assertEqual(
            result.net_pay,
            money(
                result.gross_pay
                - result.total_deductions
            ),
        )

    def test_employer_contributions_are_not_employee_deductions(self) -> None:
        result = self.build_result()

        add_payroll_lines(self.conn, 1, result)

        employer_total = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payroll_item_lines
            WHERE payroll_item_id=1
              AND kind='employer'
            """
        ).fetchone()[0]

        expected = money(
            result.sss_er
            + result.sss_ec
            + result.philhealth_er
            + result.pagibig_er
        )

        self.assertEqual(
            money(employer_total),
            expected,
        )

        self.assertNotEqual(
            money(employer_total),
            result.total_deductions,
        )

    def test_zero_value_lines_do_not_break_reconciliation(self) -> None:
        result = self.build_result()

        result.freelance_pay = 0.0
        result.other_earnings = 0.0

        result.gross_pay = money(
            result.regular_pay
            + result.holiday_pay
            + result.ot_pay
            + result.night_diff_pay
            + result.paid_leave_pay
        )

        add_payroll_lines(self.conn, 1, result)

        total = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payroll_item_lines
            WHERE payroll_item_id=1
              AND kind='earning'
            """
        ).fetchone()[0]

        self.assertEqual(
            money(total),
            result.gross_pay,
        )

        labels = {
            row["label"]
            for row in self.conn.execute(
                """
                SELECT label
                FROM payroll_item_lines
                WHERE payroll_item_id=1
                """
            ).fetchall()
        }

        self.assertNotIn("Freelance Output Pay", labels)
        self.assertNotIn("Other Earnings", labels)


if __name__ == "__main__":
    unittest.main()
