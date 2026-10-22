from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.my_payroll import my_payroll
from core.db import get_conn, init_db, now_iso


class Group14EmployeePayrollIsolationTests(unittest.TestCase):
    """Exercise the real Staff payroll SQL against two unrelated employees."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "staff-test.sqlite"
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_ENV": "test",
            "STAFF_PAYROLL_DB_PATH": str(self.path),
            "STAFF_PAYROLL_API_KEY": "",
        }):
            with get_conn(self.path) as conn:
                init_db(conn)
                stamp = now_iso()
                self.employee_ids = []
                for code, name in [("G14-A", "Staff Example A"), ("G14-B", "Staff Example B")]:
                    self.employee_ids.append(int(conn.execute(
                        """INSERT INTO employees(employee_code,full_name,department,position,status,created_at,updated_at)
                           VALUES(?,?,'Front Desk','Receptionist','Active',?,?)""",
                        (code, name, stamp, stamp),
                    ).lastrowid))
                self.user_ids = []
                for i, employee_id in enumerate(self.employee_ids):
                    self.user_ids.append(int(conn.execute(
                        """INSERT INTO app_users(display_name,role,active,must_change_password,session_version,employee_id,created_at)
                           VALUES(?, 'Staff', 1, 0, 1, ?, ?)""",
                        (f"Staff Account {i}", employee_id, stamp),
                    ).lastrowid))
                self.inactive_user_id = int(conn.execute(
                    """INSERT INTO app_users(display_name,role,active,must_change_password,session_version,employee_id,created_at)
                       VALUES('Inactive Staff Account','Staff',0,0,1,?,?)""",
                    (self.employee_ids[0], stamp),
                ).lastrowid)
                self.unlinked_user_id = int(conn.execute(
                    """INSERT INTO app_users(display_name,role,active,must_change_password,session_version,created_at)
                       VALUES('Unlinked Staff Account','Staff',1,0,1,?)""",
                    (stamp,),
                ).lastrowid)
                run_id = int(conn.execute(
                    """INSERT INTO payroll_runs(period_start,period_end,payout_date,run_label,status,created_at)
                       VALUES('2026-10-01','2026-10-14','2026-10-15','Group 14 test','Paid',?)""",
                    (stamp,),
                ).lastrowid)
                for employee_id, net in zip(self.employee_ids, (1123.50, 1987.75)):
                    conn.execute(
                        """INSERT INTO payroll_items(payroll_run_id,employee_id,gross_pay,total_deductions,net_pay)
                           VALUES(?,?,?,100,?)""",
                        (run_id, employee_id, net + 100, net),
                    )
                conn.commit()

    def payroll(self, user_id: int, *, forged_employee_id: int | None = None):
        user = {"id": user_id, "role_key": "staff"}
        if forged_employee_id is not None:
            user["employee_id"] = forged_employee_id
        with patch.dict(os.environ, {"STAFF_PAYROLL_ENV": "test", "STAFF_PAYROLL_API_KEY": ""}):
            with patch("api.my_payroll.DB_PATH", self.path):
                return my_payroll(user=user, x_api_key=None)

    def test_each_account_receives_only_its_own_payroll_item(self) -> None:
        for index, user_id in enumerate(self.user_ids):
            other = self.employee_ids[1 - index]
            result = self.payroll(user_id, forged_employee_id=other)
            self.assertTrue(result["ok"])
            self.assertEqual(result["employee"]["id"], self.employee_ids[index])
            self.assertEqual(len(result["items"]), 1)
            self.assertEqual(result["items"][0]["employee_id"], self.employee_ids[index])
            self.assertNotEqual(result["items"][0]["employee_id"], other)

    def test_inactive_and_unlinked_accounts_are_denied(self) -> None:
        for user_id in (self.inactive_user_id, self.unlinked_user_id):
            with self.assertRaises(HTTPException) as denied:
                self.payroll(user_id, forged_employee_id=self.employee_ids[0])
            self.assertEqual(denied.exception.status_code, 403)

    def test_no_staff_mutation_during_employee_payroll_read(self) -> None:
        before = self.path.read_bytes()
        self.payroll(self.user_ids[0])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
