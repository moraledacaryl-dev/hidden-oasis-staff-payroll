import unittest

from core.db import fetchall, fetchone, get_conn, init_db, now_iso
from core.integration_accounting import (
    build_cash_advance_repayment_payload,
    build_employee_payload,
    build_payroll_run_payload,
    enqueue_employee_sync,
    post_ready_outbox_to_accounting,
    post_ready_outbox_to_operations,
)
from core.integration_operations import build_operations_snapshot_payload, enqueue_operations_snapshot
from core.payroll_engine import (
    compute_payroll,
    compute_semi_monthly_withholding_tax,
    save_payroll_draft,
    update_payroll_status,
)
from core.quality import build_payroll_preflight_checks


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

    def test_scheduled_shifts_override_legacy_schedule_for_payroll(self):
        employee_id = self.add_taxable_employee(hourly_rate=200)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                shift_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                position TEXT NOT NULL DEFAULT 'Other',
                department TEXT,
                break_minutes INTEGER NOT NULL DEFAULT 60,
                status TEXT NOT NULL DEFAULT 'Draft',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes)
            VALUES(?, '2026-06-01', '09:00', '18:00', 'Manager', 'Admin', 60)
            """,
            (employee_id,),
        )
        self.conn.commit()
        result = compute_payroll(self.conn, "2026-06-01", "2026-06-15")[0]
        self.assertEqual(result.regular_hours, 7.0)

    def test_preflight_missing_logs_uses_scheduled_shifts(self):
        employee_id = self.add_taxable_employee(hourly_rate=200)
        self.conn.execute("DELETE FROM time_logs")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                shift_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                position TEXT NOT NULL DEFAULT 'Other',
                department TEXT,
                break_minutes INTEGER NOT NULL DEFAULT 60,
                status TEXT NOT NULL DEFAULT 'Draft',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes)
            VALUES(?, '2026-06-02', '08:00', '17:00', 'Manager', 'Admin', 60)
            """,
            (employee_id,),
        )
        self.conn.commit()
        checks = build_payroll_preflight_checks(self.conn, "2026-06-01", "2026-06-15")
        missing = [check for check in checks if "Scheduled workdays" in check["issue"]]
        self.assertTrue(missing)

    def test_recorded_correction_applies_to_next_saved_run(self):
        employee_id = self.add_taxable_employee(hourly_rate=200)
        original_run_id = self.save_run()
        self.conn.execute(
            """
            INSERT INTO payroll_corrections(payroll_run_id, employee_id, adjustment_type, amount, reason, apply_to_next_run, status)
            VALUES(?, ?, 'Earning', 125, 'Adjustment', 1, 'Recorded')
            """,
            (original_run_id, employee_id),
        )
        self.conn.execute(
            """
            INSERT INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes)
            VALUES(?, '2026-06-16', '08:00', '17:00', 60, 'Admin', '', 0, '')
            """,
            (employee_id,),
        )
        self.conn.execute(
            """
            INSERT INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
                attendance_status, ot_status, created_at, updated_at)
            VALUES(?, '2026-06-16', '08:00', '17:00', 'manual', 'Manual', 'Reviewed', 'None', ?, ?)
            """,
            (employee_id, now_iso(), now_iso()),
        )
        self.conn.commit()
        results = compute_payroll(self.conn, "2026-06-16", "2026-06-30")
        self.assertEqual(results[0].other_earnings, 125)
        next_run_id = save_payroll_draft(self.conn, "2026-06-16", "2026-06-30", "2026-06-30", "Regular", "Owner", results)
        correction = fetchone(self.conn, "SELECT status, applied_to_run_id FROM payroll_corrections WHERE payroll_run_id=?", (original_run_id,))
        self.assertEqual(correction["status"], "Applied")
        self.assertEqual(correction["applied_to_run_id"], next_run_id)

    def test_accounting_payload_includes_withholding_tax_when_present(self):
        self.add_taxable_employee()
        run_id = self.save_run()
        update_payroll_status(self.conn, run_id, "Reviewed", "Owner")
        update_payroll_status(self.conn, run_id, "Approved", "Owner")
        payload = build_payroll_run_payload(self.conn, run_id)
        self.assertGreater(payload["totals"]["tax"], 0)
        self.assertTrue(any(line["credit_account"] == "Withholding Tax Payable" for line in payload["journal_preview"]))
        self.assertEqual(payload["schema_version"], "2026-06-v1")
        self.assertIn("sss_er", payload["totals"])
        self.assertIn("philhealth_er", payload["totals"])
        self.assertIn("pagibig_er", payload["totals"])

    def test_employee_sync_exports_only_safe_identity_fields(self):
        self.add_taxable_employee()
        payload = build_employee_payload(self.conn)
        replay = build_employee_payload(self.conn)
        employees = payload["payload"]["employees"]
        self.assertEqual(payload["external_source"], "hidden_oasis_staff_payroll")
        self.assertEqual(payload["schema_version"], "2026-06-v1")
        self.assertEqual(payload["external_id"], replay["external_id"])
        self.assertTrue(employees)
        forbidden = {"hourly_rate", "daily_rate", "declared_monthly_base", "benefits_sss", "supervisor", "notes", "full_name"}
        self.assertFalse(forbidden.intersection(employees[0].keys()))
        self.assertLessEqual(set(employees[0].keys()), {
            "employee_code", "display_name", "department", "position", "role", "active", "primary_department", "source_staff_id"
        })

    def test_cash_advance_repayment_payload_is_enveloped(self):
        employee_id = self.add_taxable_employee(hourly_rate=200)
        now = now_iso()
        self.conn.execute(
            """
            INSERT INTO cash_advances(employee_id, request_date, amount, status, outstanding_balance, created_at)
            VALUES(?, '2026-06-02', 500, 'Approved', 250, ?)
            """,
            (employee_id, now),
        )
        ca_id = fetchone(self.conn, "SELECT id FROM cash_advances")["id"]
        self.conn.execute(
            """
            INSERT INTO cash_advance_repayments(cash_advance_id, payment_date, amount, created_at)
            VALUES(?, '2026-06-15', 250, ?)
            """,
            (ca_id, now),
        )
        self.conn.commit()
        repayment_id = fetchone(self.conn, "SELECT id FROM cash_advance_repayments")["id"]
        payload = build_cash_advance_repayment_payload(self.conn, repayment_id)
        self.assertEqual(payload["event_type"], "cash_advance.repaid")
        self.assertEqual(payload["source_record_type"], "Cash Advance Repayment")
        self.assertEqual(payload["payload"]["repayment"]["amount"], 250)

    def test_operations_snapshot_exports_counts_only(self):
        self.add_taxable_employee(hourly_rate=200)
        payload = build_operations_snapshot_payload(self.conn)
        replay = build_operations_snapshot_payload(self.conn)
        body = payload["payload"]
        self.assertEqual(payload["event_type"], "staff.operations.snapshot")
        self.assertEqual(payload["external_id"], replay["external_id"])
        self.assertIn("counts", body)
        self.assertNotIn("cards", body)
        self.assertTrue(all(isinstance(value, int) for value in body["counts"].values()))

    def test_operations_preview_query_uses_existing_attendance_status_column(self):
        row = fetchone(
            self.conn,
            """
            SELECT COUNT(*) AS c FROM time_logs
            WHERE COALESCE(attendance_status,'Pending') IN ('Pending','Disputed','Needs Manager','Needs Review')
            """,
        )
        self.assertEqual(row["c"], 0)

    def test_posts_ready_outbox_events_to_accounting_review_endpoint(self):
        self.add_taxable_employee(hourly_rate=200)
        event_id = enqueue_employee_sync(self.conn)
        calls = []

        def fake_post(url, payload_json, timeout_seconds=20, api_key=""):
            calls.append((url, payload_json, timeout_seconds, api_key))
            return {"status": "ok", "receipt_id": 12}

        import core.integration_accounting as integration_accounting

        original_post = integration_accounting._post_json
        integration_accounting._post_json = fake_post
        try:
            result = post_ready_outbox_to_accounting(self.conn, base_url="http://accounting.local/api")
        finally:
            integration_accounting._post_json = original_post

        row = fetchone(self.conn, "SELECT status, attempt_count, last_error, sent_at FROM integration_outbox WHERE id=?", (event_id,))
        self.assertEqual(result["sent"], 1)
        self.assertEqual(calls[0][0], "http://accounting.local/api/integrations/payroll/employees")
        self.assertEqual(row["status"], "Sent")
        self.assertEqual(row["attempt_count"], 1)
        self.assertEqual(row["last_error"], "")
        self.assertTrue(row["sent_at"])

    def test_posts_ready_operations_events_to_operations_review_endpoint(self):
        self.add_taxable_employee(hourly_rate=200)
        event_id = enqueue_operations_snapshot(self.conn)
        calls = []

        def fake_post(url, payload_json, timeout_seconds=20, api_key=""):
            calls.append((url, payload_json, timeout_seconds, api_key))
            return {"status": "accepted", "id": 42}

        import core.integration_accounting as integration_accounting

        original_post = integration_accounting._post_json
        integration_accounting._post_json = fake_post
        try:
            result = post_ready_outbox_to_operations(self.conn, base_url="http://operations.local/api")
        finally:
            integration_accounting._post_json = original_post

        row = fetchone(self.conn, "SELECT status, attempt_count, last_error, sent_at FROM integration_outbox WHERE id=?", (event_id,))
        self.assertEqual(result["sent"], 1)
        self.assertEqual(calls[0][0], "http://operations.local/api/integrations/staff/events")
        self.assertEqual(row["status"], "Sent")
        self.assertEqual(row["attempt_count"], 1)
        self.assertEqual(row["last_error"], "")
        self.assertTrue(row["sent_at"])

    def test_accounting_post_skips_operations_only_events(self):
        self.add_taxable_employee(hourly_rate=200)
        event_id = enqueue_operations_snapshot(self.conn)

        result = post_ready_outbox_to_accounting(self.conn, base_url="http://accounting.local/api")

        row = fetchone(self.conn, "SELECT status, attempt_count, last_error FROM integration_outbox WHERE id=?", (event_id,))
        self.assertEqual(result["attempted"], 0)
        self.assertEqual(row["status"], "Ready")
        self.assertEqual(row["attempt_count"], 0)
        self.assertIn(row["last_error"], (None, ""))


if __name__ == "__main__":
    unittest.main()
