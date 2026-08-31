from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.attendance_template_import import AttendanceTemplateImportPayload, AttendanceTemplateRow
from api.attendance_template_split_shift import import_attendance_template_v2
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import fetchall, get_conn, init_db, now_iso


class AttendanceTemplateSplitShiftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "split-shift.sqlite"
        conn = get_conn(self.db_path)
        try:
            init_db(conn)
            ensure_schedule_schema(conn)
            timestamp = now_iso()
            self.employee_id = int(
                conn.execute(
                    """
                    INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
                    VALUES('BIO-SPLIT', 'Split Shift Employee', 'Active', ?, ?)
                    """,
                    (timestamp, timestamp),
                ).lastrowid
            )
            self.shift_one = int(
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(
                        employee_id, shift_date, start_time, end_time,
                        position, department, break_minutes, status, source,
                        created_at, updated_at
                    )
                    VALUES(?, '2026-08-31', '08:00', '12:00', 'Receptionist', 'Front Office', 0, 'Draft', 'planned', ?, ?)
                    """,
                    (self.employee_id, timestamp, timestamp),
                ).lastrowid
            )
            self.shift_two = int(
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(
                        employee_id, shift_date, start_time, end_time,
                        position, department, break_minutes, status, source,
                        created_at, updated_at
                    )
                    VALUES(?, '2026-08-31', '16:00', '20:00', 'Receptionist', 'Front Office', 0, 'Draft', 'planned', ?, ?)
                    """,
                    (self.employee_id, timestamp, timestamp),
                ).lastrowid
            )
            conn.commit()
        finally:
            conn.close()
        self.actor = {"display_name": "Payroll Admin", "role_key": "payroll"}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def call_import(self, rows: list[AttendanceTemplateRow], *, dry_run: bool = False) -> dict:
        payload = AttendanceTemplateImportPayload(
            dry_run=dry_run,
            file_name="split-shift.csv",
            rows=rows,
            replace_template_rows=True,
        )
        with (
            patch("api.attendance_template_split_shift.DB_PATH", self.db_path),
            patch("api.attendance_template_split_shift.require_attendance_importer", return_value=self.actor),
        ):
            return import_attendance_template_v2(payload, authorization=None, x_api_key=None)

    def split_rows(self) -> list[AttendanceTemplateRow]:
        return [
            AttendanceTemplateRow(
                work_date="2026-08-31",
                biometric_id="BIO-SPLIT",
                time_in="8:02 AM",
                time_out="12:01 PM",
                time_out_date="2026-08-31",
                attendance_status="ON-TIME",
            ),
            AttendanceTemplateRow(
                work_date="2026-08-31",
                biometric_id="BIO-SPLIT",
                time_in="3:58 PM",
                time_out="8:03 PM",
                time_out_date="2026-08-31",
                attendance_status="ON-TIME",
            ),
        ]

    def test_two_same_day_rows_link_to_two_separate_shifts(self) -> None:
        result = self.call_import(self.split_rows())

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["imported"], 2)
        self.assertEqual(result["summary"]["shift_linked"], 2)

        conn = get_conn(self.db_path)
        try:
            rows = fetchall(
                conn,
                """
                SELECT scheduled_shift_id, actual_in, actual_out, source
                FROM time_logs
                WHERE employee_id=? AND work_date='2026-08-31'
                ORDER BY actual_in
                """,
                (self.employee_id,),
            )
        finally:
            conn.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["scheduled_shift_id"], self.shift_one)
        self.assertEqual(rows[1]["scheduled_shift_id"], self.shift_two)
        self.assertEqual(rows[0]["actual_in"], "08:02")
        self.assertEqual(rows[1]["actual_in"], "15:58")
        self.assertTrue(all(row["source"] == "template_upload" for row in rows))

    def test_reimport_replaces_group_once_without_collapsing_split_rows(self) -> None:
        self.call_import(self.split_rows())
        self.call_import(self.split_rows())

        conn = get_conn(self.db_path)
        try:
            rows = fetchall(
                conn,
                """
                SELECT scheduled_shift_id, actual_in
                FROM time_logs
                WHERE employee_id=? AND work_date='2026-08-31'
                ORDER BY actual_in
                """,
                (self.employee_id,),
            )
        finally:
            conn.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [row["scheduled_shift_id"] for row in rows],
            [self.shift_one, self.shift_two],
        )

    def test_ambiguous_split_shift_upload_is_not_guessed(self) -> None:
        result = self.call_import(
            [
                AttendanceTemplateRow(
                    work_date="2026-08-31",
                    biometric_id="BIO-SPLIT",
                    time_in="8:02 AM",
                    time_out="12:01 PM",
                    time_out_date="2026-08-31",
                    attendance_status="ON-TIME",
                )
            ],
            dry_run=True,
        )

        self.assertEqual(result["summary"]["shift_linked"], 0)
        self.assertEqual(result["summary"]["needs_review"], 1)
        self.assertEqual(result["items"][0]["shift_match_mode"], "ambiguous_split_shift")
        self.assertIn("exactly one attendance row per shift", result["items"][0]["issues"][-1])


if __name__ == "__main__":
    unittest.main()
