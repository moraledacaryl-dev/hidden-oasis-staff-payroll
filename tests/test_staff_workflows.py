from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.staff_published_portal import (
    StaffLeaveRequestPayload,
    submit_leave_request,
    withdraw_leave_request,
)
from api.staff_self_service import (
    ShiftChangeDecisionPayload,
    ShiftChangeRequestPayload,
    confirm_shift_swap,
    decide_shift_change_request,
    submit_shift_change_request,
)
from core.db import fetchall, fetchone, get_conn, init_db, now_iso


class StaffWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "staff.sqlite"
        conn = get_conn(self.db_path)
        try:
            init_db(conn)
            conn.execute(
                """
                INSERT INTO employees(
                    employee_code, full_name, department, position, status, created_at, updated_at
                )
                VALUES
                  ('E-1','Staff One','Reception','Receptionist','Active',?,?),
                  ('E-2','Staff Two','Reception','Receptionist','Active',?,?)
                """,
                (now_iso(), now_iso(), now_iso(), now_iso()),
            )
            first = int(fetchone(conn, "SELECT id FROM employees WHERE employee_code='E-1'")["id"])
            second = int(fetchone(conn, "SELECT id FROM employees WHERE employee_code='E-2'")["id"])
            conn.execute(
                """
                INSERT INTO app_users(display_name, role, active, employee_id, session_version, created_at)
                VALUES
                  ('Staff One','Staff',1,?,1,?),
                  ('Staff Two','Staff',1,?,1,?),
                  ('Owner','Owner',1,NULL,1,?)
                """,
                (first, now_iso(), second, now_iso(), now_iso()),
            )
            conn.execute(
                """
                INSERT INTO scheduled_shifts(
                    employee_id, shift_date, start_time, end_time, position, department,
                    status, created_at, updated_at
                ) VALUES
                  (?, '2026-07-01', '08:00', '17:00', 'Receptionist', 'Reception', 'Confirmed', ?, ?),
                  (?, '2026-07-02', '10:00', '19:00', 'Receptionist', 'Reception', 'Confirmed', ?, ?)
                """,
                (first, now_iso(), now_iso(), second, now_iso(), now_iso()),
            )
            leave_type = int(
                fetchone(conn, "SELECT id FROM leave_types WHERE name='Service Incentive Leave'")[
                    "id"
                ]
            )
            conn.execute(
                """
                INSERT INTO employee_leave_entitlements(
                    employee_id, leave_type_id, year, credits, used, entitled
                ) VALUES(?,?,2026,5,0,1)
                """,
                (first, leave_type),
            )
            conn.commit()
            self.first_employee = first
            self.second_employee = second
            self.first_user = dict(
                fetchone(conn, "SELECT * FROM app_users WHERE display_name='Staff One'")
            )
            self.second_user = dict(
                fetchone(conn, "SELECT * FROM app_users WHERE display_name='Staff Two'")
            )
            self.owner_user = {
                **dict(fetchone(conn, "SELECT * FROM app_users WHERE display_name='Owner'")),
                "role_key": "owner",
            }
            self.leave_type = leave_type
            self.first_shift = int(
                fetchone(
                    conn,
                    "SELECT id FROM scheduled_shifts WHERE employee_id=?",
                    (first,),
                )["id"]
            )
            self.second_shift = int(
                fetchone(
                    conn,
                    "SELECT id FROM scheduled_shifts WHERE employee_id=?",
                    (second,),
                )["id"]
            )
        finally:
            conn.close()
        self.first_user["role_key"] = "staff"
        self.second_user["role_key"] = "staff"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_confirmed_swap_exchanges_both_assignments_atomically(self):
        with patch("api.staff_self_service.DB_PATH", self.db_path):
            submitted = submit_shift_change_request(
                ShiftChangeRequestPayload(
                    shift_id=self.first_shift,
                    request_type="Shift Swap",
                    reason="Trade shifts",
                    proposed_swap_employee_id=self.second_employee,
                    proposed_swap_shift_id=self.second_shift,
                ),
                user=self.first_user,
                x_api_key=None,
            )
            confirm_shift_swap(
                submitted["request_id"],
                user=self.second_user,
                x_api_key=None,
            )
            result = decide_shift_change_request(
                submitted["request_id"],
                ShiftChangeDecisionPayload(
                    decision="Approved",
                    coverage_confirmed=True,
                    employee_notified=True,
                ),
                user=self.owner_user,
                x_api_key=None,
            )
        self.assertTrue(result["applied"])
        conn = get_conn(self.db_path)
        try:
            first = fetchone(conn, "SELECT employee_id FROM scheduled_shifts WHERE id=?", (self.first_shift,))
            second = fetchone(conn, "SELECT employee_id FROM scheduled_shifts WHERE id=?", (self.second_shift,))
            changes = fetchall(
                conn,
                "SELECT * FROM schedule_change_logs WHERE change_type='Shift swap approved'",
            )
        finally:
            conn.close()
        self.assertEqual(first["employee_id"], self.second_employee)
        self.assertEqual(second["employee_id"], self.first_employee)
        self.assertEqual(len(changes), 2)

    def test_swap_is_blocked_when_destination_employee_has_overlap(self):
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO scheduled_shifts(
                    employee_id, shift_date, start_time, end_time, position, department,
                    status, created_at, updated_at
                ) VALUES(?, '2026-07-01', '08:30', '12:00', 'Receptionist', 'Reception',
                         'Confirmed', ?, ?)
                """,
                (self.second_employee, now_iso(), now_iso()),
            )
            conn.commit()
        finally:
            conn.close()

        with patch("api.staff_self_service.DB_PATH", self.db_path):
            submitted = submit_shift_change_request(
                ShiftChangeRequestPayload(
                    shift_id=self.first_shift,
                    request_type="Shift Swap",
                    reason="Trade shifts",
                    proposed_swap_employee_id=self.second_employee,
                    proposed_swap_shift_id=self.second_shift,
                ),
                user=self.first_user,
                x_api_key=None,
            )
            confirm_shift_swap(
                submitted["request_id"],
                user=self.second_user,
                x_api_key=None,
            )
            with self.assertRaises(HTTPException) as blocked:
                decide_shift_change_request(
                    submitted["request_id"],
                    ShiftChangeDecisionPayload(decision="Approved"),
                    user=self.owner_user,
                    x_api_key=None,
                )
        self.assertEqual(blocked.exception.status_code, 409)

    def test_leave_request_reserves_balance_and_can_be_withdrawn(self):
        with patch("api.staff_published_portal.DB_PATH", self.db_path):
            submitted = submit_leave_request(
                StaffLeaveRequestPayload(
                    leave_type_id=self.leave_type,
                    start_date=date(2026, 7, 6),
                    end_date=date(2026, 7, 7),
                    reason="Family appointment",
                ),
                user=self.first_user,
                x_api_key=None,
            )
            withdrawn = withdraw_leave_request(
                submitted["request_id"],
                user=self.first_user,
                x_api_key=None,
            )
        self.assertEqual(withdrawn["status"], "Withdrawn")
        conn = get_conn(self.db_path)
        try:
            row = fetchone(
                conn,
                "SELECT status, decision_note FROM leave_requests WHERE id=?",
                (submitted["request_id"],),
            )
            audit = fetchone(
                conn,
                """
                SELECT COUNT(*) AS c FROM audit_logs
                WHERE table_name='leave_requests' AND record_id=?
                """,
                (submitted["request_id"],),
            )
        finally:
            conn.close()
        self.assertEqual(row["status"], "Withdrawn")
        self.assertEqual(row["decision_note"], "Withdrawn by employee")
        self.assertEqual(int(audit["c"]), 2)

    def test_unpaid_leave_does_not_require_paid_credits(self):
        conn = get_conn(self.db_path)
        try:
            unpaid_type = int(
                fetchone(conn, "SELECT id FROM leave_types WHERE name='Unpaid Leave'")["id"]
            )
        finally:
            conn.close()
        with patch("api.staff_published_portal.DB_PATH", self.db_path):
            submitted = submit_leave_request(
                StaffLeaveRequestPayload(
                    leave_type_id=unpaid_type,
                    start_date=date(2026, 8, 3),
                    end_date=date(2026, 8, 4),
                    reason="Personal leave",
                ),
                user=self.first_user,
                x_api_key=None,
            )
        self.assertEqual(submitted["status"], "Pending")


if __name__ == "__main__":
    unittest.main()
