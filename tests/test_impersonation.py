from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.impersonation import StartImpersonationRequest, start_impersonation
from api.main import (
    AttendanceDecisionRequest,
    current_user_from_token,
    log_impersonated_action,
    sign_payload,
)
from api.server import app
from core.db import fetchall, fetchone, get_conn, init_db, now_iso


class OwnerImpersonationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "impersonation.sqlite"
        self.env = patch.dict(
            os.environ,
            {
                "STAFF_PAYROLL_DB_PATH": str(self.db_path),
                "STAFF_PAYROLL_SESSION_SECRET": "impersonation-test-secret",
                "STAFF_PAYROLL_API_KEY": "",
                "STAFF_PAYROLL_ENV": "test",
            },
        )
        self.env.start()
        conn = get_conn(self.db_path)
        try:
            init_db(conn)
            stamp = now_iso()
            self.employee_id = int(
                conn.execute(
                    """
                    INSERT INTO employees(
                        employee_code,full_name,department,position,status,created_at,updated_at
                    ) VALUES('VIEW-1','View Test Staff','Operations','Staff','Active',?,?)
                    """,
                    (stamp, stamp),
                ).lastrowid
            )
            self.owner_id = self.add_user(conn, "View Test Owner", "Owner")
            self.supervisor_id = self.add_user(conn, "View Test Manager", "General Manager")
            self.staff_id = self.add_user(conn, "View Test Staff", "Staff", self.employee_id)
            self.unlinked_staff_id = self.add_user(conn, "Unlinked Staff", "Staff")
            self.payroll_id = self.add_user(conn, "Payroll User", "Payroll")
            self.time_log_id = int(
                conn.execute(
                    """
                    INSERT INTO time_logs(
                        employee_id,work_date,actual_in,actual_out,source,verification_type,
                        attendance_status,ot_status,created_at,updated_at
                    ) VALUES(?, '2026-07-01', '08:00', '17:00', 'manual', 'Manual',
                             'Needs Review', 'None', ?, ?)
                    """,
                    (self.employee_id, stamp, stamp),
                ).lastrowid
            )
            conn.commit()
        finally:
            conn.close()
        self.owner_token = sign_payload(
            {"sub": self.owner_id, "role": "owner", "sv": 1, "exp": 4_102_444_800}
        )

    def tearDown(self) -> None:
        self.env.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def add_user(conn, display_name: str, role: str, employee_id: int | None = None) -> int:
        return int(
            conn.execute(
                """
                INSERT INTO app_users(
                    display_name,role,active,must_change_password,session_version,created_at,employee_id
                ) VALUES(?,?,1,0,1,?,?)
                """,
                (display_name, role, now_iso(), employee_id),
            ).lastrowid
        )

    def start_view(self, target_user_id: int) -> dict:
        with patch("api.impersonation.DB_PATH", self.db_path):
            return start_impersonation(
                StartImpersonationRequest(target_user_id=target_user_id),
                authorization=f"Bearer {self.owner_token}",
                x_api_key=None,
            )

    def test_owner_can_view_supervisor_and_linked_staff_without_passwords(self) -> None:
        for user_id, role in (
            (self.supervisor_id, "supervisor"),
            (self.staff_id, "staff"),
        ):
            result = self.start_view(user_id)
            viewed = current_user_from_token(f"Bearer {result['access_token']}")
            self.assertEqual(viewed["id"], user_id)
            self.assertEqual(viewed["role_key"], role)
            self.assertEqual(viewed["is_impersonating"], 1)
            self.assertEqual(viewed["impersonator_id"], self.owner_id)
            self.assertEqual(result["expires_in"], 1800)

    def test_ineligible_accounts_are_rejected(self) -> None:
        for user_id in (self.owner_id, self.payroll_id):
            with self.assertRaises(HTTPException) as raised:
                self.start_view(user_id)
            self.assertEqual(raised.exception.status_code, 422)
        with self.assertRaises(HTTPException) as unlinked:
            self.start_view(self.unlinked_staff_id)
        self.assertEqual(unlinked.exception.status_code, 409)

    def test_owner_session_revocation_invalidates_view_session(self) -> None:
        token = self.start_view(self.supervisor_id)["access_token"]
        conn = get_conn(self.db_path)
        try:
            conn.execute("UPDATE app_users SET session_version=2 WHERE id=?", (self.owner_id,))
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(HTTPException) as raised:
            current_user_from_token(f"Bearer {token}")
        self.assertEqual(raised.exception.status_code, 401)

    def test_supervisor_write_succeeds_and_records_owner_attribution(self) -> None:
        token = self.start_view(self.supervisor_id)["access_token"]
        viewed = current_user_from_token(f"Bearer {token}")
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/v1/attendance/time-logs/{time_log_id}/decision"
            and "POST" in getattr(route, "methods", set())
        )
        result = route.endpoint(
            self.time_log_id,
            AttendanceDecisionRequest(
                decision="Approved",
                reason="Checked while viewing manager",
                approved_ot_hours=0,
            ),
            user=viewed,
        )
        self.assertTrue(result["ok"])
        log_impersonated_action(
            {
                "owner_id": self.owner_id,
                "owner_name": "View Test Owner",
                "target_id": self.supervisor_id,
                "target_name": "View Test Manager",
            },
            method="POST",
            path=f"/api/v1/attendance/time-logs/{self.time_log_id}/decision",
            status_code=200,
            ip_address="127.0.0.1",
        )

        conn = get_conn(self.db_path)
        try:
            time_log = fetchone(
                conn,
                "SELECT attendance_status FROM time_logs WHERE id=?",
                (self.time_log_id,),
            )
            audit_rows = fetchall(
                conn,
                "SELECT actor,action,record_id,details FROM audit_logs WHERE action='Owner acted as user'",
            )
        finally:
            conn.close()
        self.assertEqual(time_log["attendance_status"], "Approved")
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0]["actor"], "View Test Owner")
        self.assertEqual(audit_rows[0]["record_id"], self.supervisor_id)
        details = json.loads(audit_rows[0]["details"])
        self.assertEqual(details["target"], "View Test Manager")
        self.assertEqual(details["owner_id"], self.owner_id)
        self.assertEqual(details["method"], "POST")
        self.assertEqual(
            details["path"],
            f"/api/v1/attendance/time-logs/{self.time_log_id}/decision",
        )


if __name__ == "__main__":
    unittest.main()
