from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.attendance_compliance import attendance_compliance, ensure_schema
from core.db import get_conn, init_db, now_iso


class AttendanceComplianceContractTests(unittest.TestCase):
    def test_response_keeps_supervisor_ui_contract_with_canonical_shifts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "attendance.sqlite"
            conn = get_conn(db_path)
            try:
                init_db(conn)
                ensure_schema(conn)
                stamp = now_iso()
                employee_id = int(
                    conn.execute(
                        """
                        INSERT INTO employees(
                            employee_code, full_name, department, position, status,
                            created_at, updated_at
                        ) VALUES('ATT-1','Attendance Person','Operations',
                                 'Receptionist','Active',?,?)
                        """,
                        (stamp, stamp),
                    ).lastrowid
                )
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(
                        employee_id, shift_date, start_time, end_time, position,
                        department, break_minutes, status, source
                    ) VALUES(?, '2026-07-02', '08:00', '17:00', 'Receptionist',
                             'Operations', 60, 'Draft', 'planned')
                    """,
                    (employee_id,),
                )
                conn.execute(
                    """
                    INSERT INTO time_logs(
                        employee_id, work_date, actual_in, actual_out, source,
                        attendance_status, created_at, updated_at
                    ) VALUES(?, '2026-07-02', '08:10', '17:00', 'manual',
                             'Approved', ?, ?)
                    """,
                    (employee_id, stamp, stamp),
                )
                conn.execute(
                    """
                    INSERT INTO attendance_memos(
                        employee_id, period_month, memo_type, memo_level, reason,
                        status, issued_by, issued_at
                    ) VALUES(?, '2026-07', 'Attendance', 'Verbal', 'Late arrival',
                             'Issued', 'Browser Owner', ?)
                    """,
                    (employee_id, stamp),
                )
                conn.commit()
            finally:
                conn.close()

            with (
                patch("api.attendance_compliance.DB_PATH", db_path),
                patch(
                    "api.attendance_compliance.require_attendance_compliance_user",
                    return_value={"display_name": "Browser Owner", "role_key": "owner"},
                ),
            ):
                result = attendance_compliance(
                    month="2026-07",
                    authorization=None,
                    x_api_key=None,
                )

        self.assertEqual(result["mode"], "attendance_compliance_scheduled_shifts_only")
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["full_name"], "Attendance Person")
        self.assertEqual(item["employee_code"], "ATT-1")
        self.assertEqual(item["scheduled_shifts"], 1)
        self.assertEqual(item["late_infractions"], 1)
        self.assertEqual(item["late_details"][0]["minutes_late"], 10)
        self.assertIn("handbook_action", item)
        self.assertIn("attendance_reward_status", item)
        self.assertEqual(result["memos"][0]["full_name"], "Attendance Person")


if __name__ == "__main__":
    unittest.main()
