from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.attendance_template_import import (
    AttendanceTemplateImportPayload,
    AttendanceTemplateRow,
    import_attendance_template,
)
from core.db import fetchone, get_conn, init_db, now_iso


class AttendanceTemplateImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "attendance-template.sqlite"
        conn = get_conn(self.db_path)
        try:
            init_db(conn)
            timestamp = now_iso()
            self.employee_id = int(
                conn.execute(
                    """
                    INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
                    VALUES('BIO-1', 'Template Employee', 'Active', ?, ?)
                    """,
                    (timestamp, timestamp),
                ).lastrowid
            )
            conn.commit()
        finally:
            conn.close()
        self.actor = {"display_name": "Payroll Admin", "role_key": "payroll"}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def call_import(self, payload: AttendanceTemplateImportPayload) -> dict:
        with (
            patch("api.attendance_template_import.DB_PATH", self.db_path),
            patch("api.attendance_template_import.require_attendance_importer", return_value=self.actor),
        ):
            return import_attendance_template(payload, authorization=None, x_api_key=None)

    def test_preview_accepts_clean_overnight_template_row(self) -> None:
        result = self.call_import(
            AttendanceTemplateImportPayload(
                dry_run=True,
                rows=[
                    AttendanceTemplateRow(
                        work_date="2026-06-16",
                        employee_name="Template Employee",
                        time_in="6:55 PM",
                        time_out="7:02 AM",
                        time_out_date="2026-06-17",
                        attendance_status="ON-TIME",
                    )
                ],
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["ready"], 1)
        self.assertEqual(result["summary"]["errors"], 0)
        self.assertEqual(result["items"][0]["actual_in"], "18:55")
        self.assertEqual(result["items"][0]["actual_out"], "07:02")

    def test_preview_flags_overnight_without_time_out_date(self) -> None:
        result = self.call_import(
            AttendanceTemplateImportPayload(
                dry_run=True,
                rows=[
                    AttendanceTemplateRow(
                        work_date="2026-06-16",
                        employee_name="Template Employee",
                        time_in="6:55 PM",
                        time_out="7:02 AM",
                        attendance_status="ON-TIME",
                    )
                ],
            )
        )

        self.assertEqual(result["summary"]["needs_review"], 1)
        self.assertIn("time_out is earlier than time_in", result["items"][0]["issues"][0])

    def test_import_writes_template_upload_time_log(self) -> None:
        result = self.call_import(
            AttendanceTemplateImportPayload(
                dry_run=False,
                file_name="attendance.csv",
                rows=[
                    AttendanceTemplateRow(
                        work_date="2026-06-16",
                        biometric_id="BIO-1",
                        time_in="5:52 AM",
                        time_out="3:01 PM",
                        time_out_date="2026-06-16",
                        attendance_status="ON-TIME",
                    )
                ],
            )
        )
        self.assertEqual(result["summary"]["imported"], 1)

        conn = get_conn(self.db_path)
        try:
            row = fetchone(
                conn,
                """
                SELECT employee_id, work_date, actual_in, actual_out, source, attendance_status
                FROM time_logs
                WHERE employee_id=?
                """,
                (self.employee_id,),
            )
        finally:
            conn.close()

        self.assertEqual(row["employee_id"], self.employee_id)
        self.assertEqual(row["work_date"], "2026-06-16")
        self.assertEqual(row["actual_in"], "05:52")
        self.assertEqual(row["actual_out"], "15:01")
        self.assertEqual(row["source"], "template_upload")
        self.assertEqual(row["attendance_status"], "ON-TIME")


if __name__ == "__main__":
    unittest.main()
