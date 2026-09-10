from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError
from api.employees import EmployeeEditorPayload, add_employee, edit_employee
from api.main import normalize_employee
from core.db import get_conn, init_db, run_schema_migrations


class UiAuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite"
        with get_conn(self.path) as conn:
            init_db(conn)
        self.patch = patch("api.employees.configured_db_path", return_value=self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_payroll_editor_preserves_money_and_redacts_manager_read(self):
        payload = EmployeeEditorPayload(employee_code="QA1", full_name="Audit Worker", hourly_rate=123.45, declared_monthly_base=23456.78)
        employee_id = add_employee(payload, {"role_key": "owner", "display_name": "Owner"})["employee_id"]
        with get_conn(self.path) as conn:
            row = dict(conn.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone())
        self.assertEqual(normalize_employee(row)["hourly_rate"], 123.45)
        self.assertEqual(normalize_employee(row)["declared_monthly_base"], 23456.78)
        self.assertIsNone(normalize_employee(row, include_private=False)["hourly_rate"])
        self.assertIsNone(normalize_employee(row, include_private=False)["declared_monthly_base"])
        edit_employee(employee_id, EmployeeEditorPayload(employee_code="QA1", full_name="Audit Worker", position="Reception"), {"role_key": "supervisor", "display_name": "Manager"})
        with get_conn(self.path) as conn:
            row = dict(conn.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone())
        self.assertEqual(row["hourly_rate"], 123.45)
        self.assertEqual(row["declared_monthly_base"], 23456.78)
        with self.assertRaises(HTTPException) as failure:
            edit_employee(employee_id, payload, {"role_key": "supervisor"})
        self.assertEqual(failure.exception.status_code, 403)

    def test_invalid_compensation_and_duplicate_do_not_create_records(self):
        for amount in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValidationError):
                EmployeeEditorPayload(employee_code="QA", full_name="Worker", hourly_rate=amount)
        payload = EmployeeEditorPayload(employee_code="QA", full_name="Worker")
        first = add_employee(payload, {"role_key": "payroll"})
        with self.assertRaises(HTTPException) as failure:
            add_employee(payload, {"role_key": "payroll"})
        self.assertEqual(failure.exception.status_code, 409)
        self.assertIn(f"#{first['employee_id']}", failure.exception.detail)
        with get_conn(self.path) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM employees").fetchone()[0], 1)

    def test_fresh_and_existing_databases_restrict_disciplinary_leave(self):
        with get_conn(self.path) as conn:
            for name in ("AWOL", "Suspension"):
                self.assertEqual(conn.execute("SELECT staff_requestable FROM leave_types WHERE name=?", (name,)).fetchone()[0], 0)
            conn.execute("UPDATE leave_types SET staff_requestable=1 WHERE name IN ('AWOL','Suspension')")
            conn.execute("DELETE FROM schema_migrations WHERE version=7")
            run_schema_migrations(conn)
            run_schema_migrations(conn)
            self.assertEqual(conn.execute("SELECT count(*) FROM leave_types WHERE name IN ('AWOL','Suspension') AND staff_requestable=1").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT staff_requestable FROM leave_types WHERE name='Unpaid Leave'").fetchone()[0], 1)

if __name__ == "__main__":
    unittest.main()
