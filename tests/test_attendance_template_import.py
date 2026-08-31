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
from core.db import fetchall, fetchone, get_conn, init_db, now_iso


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

    def add_split_shifts(self, work_date: str = "2026-06-16") -> tuple[int, int]:
        conn = get_conn(self.db_path)
        try:
            conn.execute(
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
            first = int(
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time)
                    VALUES (?, ?, '06:00', '14:00')
                    """,
                    (self.employee_id, work_date),
                ).lastrowid
            )
            second = int(
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time)
                    VALUES (?, ?, '14:00', '22:00')
                    """,
                    (self.employee_id, work_date),
                ).lastrowid
            )
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(time_logs)").fetchall()}
            if "scheduled_shift_id" not in columns:
                conn.execute("ALTER TABLE time_logs ADD COLUMN scheduled_shift_id INTEGER")
            conn.commit()
            return first, second
        finally:
            conn.close()

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

    def test_split_shift_import_preserves_two_rows_and_links_each_exact_shift(self) -> None:
        first_shift_id, second_shift_id = self.add_split_shifts()
        payload = AttendanceTemplateImportPayload(
            dry_run=False,
            file_name="split-shifts.csv",
            replace_template_rows=True,
            rows=[
                AttendanceTemplateRow(
                    work_date="2026-06-16",
                    biometric_id="BIO-1",
                    time_in="6:05 AM",
                    time_out="1:55 PM",
                    attendance_status="ON-TIME",
                ),
                AttendanceTemplateRow(
                    work_date="2026-06-16",
                    biometric_id="BIO-1",
                    time_in="2:05 PM",
                    time_out="9:55 PM",
                    attendance_status="ON-TIME",
                ),
            ],
        )

        result = self.call_import(payload)
        self.assertEqual(result["summary"]["imported"], 2)
        self.assertEqual(result["summary"]["ready"], 2)
        self.assertEqual(
            [item["scheduled_shift_id"] for item in result["items"]],
            [first_shift_id, second_shift_id],
        )

        conn = get_conn(self.db_path)
        try:
            rows = fetchall(
                conn,
                """
                SELECT scheduled_shift_id, actual_in, actual_out
                FROM time_logs
                WHERE employee_id=? AND work_date=? AND source='template_upload'
                ORDER BY actual_in
                """,
                (self.employee_id, "2026-06-16"),
            )
        finally:
            conn.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [row["scheduled_shift_id"] for row in rows],
            [first_shift_id, second_shift_id],
        )
        self.assertEqual([row["actual_in"] for row in rows], ["06:05", "14:05"])

        # Replacing the same uploaded employee/date must replace the batch as a
        # set, not delete the first split-shift row while inserting the second.
        second_result = self.call_import(payload)
        self.assertEqual(second_result["summary"]["imported"], 2)
        conn = get_conn(self.db_path)
        try:
            count = int(
                fetchone(
                    conn,
                    """
                    SELECT COUNT(*) AS total
                    FROM time_logs
                    WHERE employee_id=? AND work_date=? AND source='template_upload'
                    """,
                    (self.employee_id, "2026-06-16"),
                )["total"]
            )
        finally:
            conn.close()
        self.assertEqual(count, 2)

    def test_split_shift_preview_refuses_ambiguous_assignment(self) -> None:
        self.add_split_shifts()
        result = self.call_import(
            AttendanceTemplateImportPayload(
                dry_run=True,
                rows=[
                    AttendanceTemplateRow(
                        work_date="2026-06-16",
                        biometric_id="BIO-1",
                        time_in="11:30 PM",
                        time_out="11:45 PM",
                        attendance_status="ON-TIME",
                    )
                ],
            )
        )

        self.assertEqual(result["summary"]["needs_review"], 1)
        self.assertIsNone(result["items"][0]["scheduled_shift_id"])
        self.assertIn("does not identify exactly one shift", result["items"][0]["issues"][-1])


if __name__ == "__main__":
    unittest.main()
