import unittest

from core.db import fetchall, fetchone, get_conn, init_db, now_iso
from core.integration_accounting import build_payroll_run_payload
from core.payroll_engine import (
    compute_payroll,
    compute_semi_monthly_withholding_tax,
    save_payroll_draft,
    update_payroll_status,
)


class PayrollCoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        self.conn.execute("DELETE FROM employees")
        self.conn.commit()

    def add_taxable_employee(self, hourly_rate=3000):
        now = now_iso()
        self.conn.execute(
            """
            INSERT INTO employees(employee_code, full_name, department, position, employment_type, status,
                hourly_rate, daily_rate, declared_monthly_base, standard_shift_hours, unpaid_break_minutes,
                security_no_break, benefits_sss, benefits_philhealth, benefits_pagibig, benefits_tax,
                created_at, updated_at)
            VALUES('TAX-001', 'Taxable Employee', 'Admin', 'Manager', 'Hourly', 'Active',
                ?, 0, 0, 9, 60, 0, 0, 0, 0, 1, ?, ?)
            """,
            (hourly_rate, now, now),
        )
        employee_id = fetchone(self.conn, "SELECT id FROM employees WHERE employee_code='TAX-001'")["id"]
        self.conn.execute(
            """
            INSERT INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes)
            VALUES(?, '2026-06-01', '08:00', '17:00', 60, 'Admin', '', 0, '')
            """,
            (employee_id,),
        )
        self.conn.execute(
            """
            INSERT INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
                attendance_status, ot_status, created_at, updated_at)
            VALUES(?, '2026-06-01', '08:00', '17:00', 'manual', 'Manual', 'Reviewed', 'None', ?, ?)
            """,
            (employee_id, now, now),
        )
        self.conn.commit()
        return employee_id

    def save_run(self):
        results = compute_payroll(self.conn, "2026-06-01", "2026-06-15")
        return save_payroll_draft(
            self.conn,
            "2026-06-01",
            "2026-06-15",
            "2026-06-15",
            "Regular",
            "Owner",
            results,
        )

    def test_semi_monthly_tax_table_keeps_minimum_income_zero(self):
        self.assertEqual(compute_semi_monthly_withholding_tax(10417), 0)
        self.assertEqual(compute_semi_monthly_withholding_tax(0), 0)
        self.assertEqual(compute_semi_monthly_withholding_tax(16667), 937.50)

    def test_tax_is_opt_in_and_saved_as_payroll_line_when_nonzero(self):
        self.add_taxable_employee()
        run_id = self.save_run()
        item = fetchone(self.conn, "SELECT * FROM payroll_items WHERE payroll_run_id=?", (run_id,))
        self.assertGreater(item["tax"], 0)
        lines = fetchall(self.conn, "SELECT label, amount FROM payroll_item_lines WHERE payroll_item_id=?", (item["id"],))
        tax_lines = [line for line in lines if line["label"] == "Withholding Tax"]
        self.assertEqual(len(tax_lines), 1)
        self.assertEqual(round(tax_lines[0]["amount"], 2), round(item["tax"], 2))

    def test_status_machine_blocks_skipping_to_paid(self):
        self.add_taxable_employee(hourly_rate=200)
        run_id = self.save_run()
        with self.assertRaises(ValueError):
            update_payroll_status(self.conn, run_id, "Paid", "Owner")
        update_payroll_status(self.conn, run_id, "Reviewed", "Owner")
        update_payroll_status(self.conn, run_id, "Approved", "Owner")
        update_payroll_status(self.conn, run_id, "Paid", "Owner")
        run = fetchone(self.conn, "SELECT status FROM payroll_runs WHERE id=?", (run_id,))
        self.assertEqual(run["status"], "Paid")

    def test_accounting_payload_includes_withholding_tax_when_present(self):
        self.add_taxable_employee()
        run_id = self.save_run()
        update_payroll_status(self.conn, run_id, "Reviewed", "Owner")
        update_payroll_status(self.conn, run_id, "Approved", "Owner")
        payload = build_payroll_run_payload(self.conn, run_id)
        self.assertGreater(payload["totals"]["tax"], 0)
        self.assertTrue(any(line["credit_account"] == "Withholding Tax Payable" for line in payload["journal_preview"]))

    def test_operations_preview_query_uses_existing_attendance_status_column(self):
        row = fetchone(
            self.conn,
            """
            SELECT COUNT(*) AS c FROM time_logs
            WHERE COALESCE(attendance_status,'Pending') IN ('Pending','Disputed','Needs Manager','Needs Review')
            """,
        )
        self.assertEqual(row["c"], 0)


if __name__ == "__main__":
    unittest.main()
