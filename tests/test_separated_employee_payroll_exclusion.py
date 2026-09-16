from __future__ import annotations

import unittest

from core.db import get_conn, init_db, now_iso
from core.payroll_engine import compute_payroll


class SeparatedEmployeePayrollExclusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        self.conn.execute("DELETE FROM employees")
        stamp = now_iso()
        for code, name, status in (
            ("ACTIVE-001", "Active Employee", "Active"),
            ("SEP-001", "Separated Employee", "Separated"),
        ):
            self.conn.execute(
                """
                INSERT INTO employees(
                    employee_code,full_name,department,position,employment_type,status,
                    hourly_rate,daily_rate,declared_monthly_base,standard_shift_hours,
                    unpaid_break_minutes,security_no_break,benefits_sss,benefits_philhealth,
                    benefits_pagibig,benefits_tax,created_at,updated_at
                ) VALUES(?,?, 'Admin','Tester','Hourly',?,100,0,0,8,0,0,0,0,0,0,?,?)
                """,
                (code, name, status, stamp, stamp),
            )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_separated_employee_is_not_returned_by_canonical_payroll(self) -> None:
        results = compute_payroll(self.conn, "2026-09-01", "2026-09-15")
        self.assertEqual([row.full_name for row in results], ["Active Employee"])


if __name__ == "__main__":
    unittest.main()
