from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.attendance_template_import import (
    AttendanceTemplateImportPayload,
    AttendanceTemplateRow,
    import_attendance_template,
    require_attendance_importer,
)
from api.main import AttendanceDecisionRequest, app, attendance_exception_sql
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
        self.actor = {"display_name": "Owner", "role_key": "owner"}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def call_import(self, payload: AttendanceTemplateImportPayload) -> dict:
        with (
            patch("api.attendance_template_import.DB_PATH", self.db_path),
            patch("api.attendance_template_import.require_attendance_importer", return_value=self.actor),
        ):
            return import_attendance_template(payload, authorization=None, x_api_key=None)

    def decide(self, time_log_id: int, decision: str) -> dict:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/v1/attendance/time-logs/{time_log_id}/decision"
            and "POST" in getattr(route, "methods", set())
        )
        with patch("api.main.configured_db_path", return_value=self.db_path):
            return route.endpoint(
                time_log_id,
                AttendanceDecisionRequest(decision=decision, reason="Reviewed"),
                user={"display_name": "General Manager", "role_key": "supervisor"},
            )

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

        self.assertEqual(result["summary"]["errors"], 1)
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
        self.assertEqual(row["attendance_status"], "Approved")

    def test_import_auto_approves_normal_rows_and_routes_only_policy_exceptions(self) -> None:
        conn = get_conn(self.db_path)
        try:
            stamp = now_iso()
            employee_ids: dict[str, int] = {"NORMAL": self.employee_id}
            conn.execute(
                "UPDATE employees SET employee_code='NORMAL', full_name='Normal Employee' WHERE id=?",
                (self.employee_id,),
            )
            for code in ("VARIANCE", "ABSENT", "REST", "LEAVE", "UNSCHEDULED"):
                employee_ids[code] = int(
                    conn.execute(
                        """
                        INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
                        VALUES(?, ?, 'Active', ?, ?)
                        """,
                        (code, f"{code.title()} Employee", stamp, stamp),
                    ).lastrowid
                )
            for code in ("NORMAL", "VARIANCE", "ABSENT", "LEAVE"):
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(
                        employee_id, shift_date, start_time, end_time,
                        position, department, break_minutes, source
                    ) VALUES(?, '2026-07-06', '08:00', '17:00',
                             'Staff', 'Operations', 60, 'planned')
                    """,
                    (employee_ids[code],),
                )
            conn.execute(
                """
                INSERT INTO schedule_day_markers(
                    employee_id, work_date, marker_type, active,
                    created_by, created_at, updated_by, updated_at
                ) VALUES(?, '2026-07-06', 'Rest Day', 1, 'Owner', ?, 'Owner', ?)
                """,
                (employee_ids["REST"], stamp, stamp),
            )
            leave_type = fetchone(conn, "SELECT id FROM leave_types WHERE name='Vacation Leave'")
            conn.execute(
                """
                INSERT INTO leave_requests(
                    employee_id, leave_type_id, start_date, end_date,
                    days, paid, status, reason, created_at
                ) VALUES(?, ?, '2026-07-06', '2026-07-06',
                         1, 1, 'Approved', 'Approved vacation', ?)
                """,
                (employee_ids["LEAVE"], leave_type["id"], stamp),
            )
            conn.commit()
        finally:
            conn.close()

        rows = [
            AttendanceTemplateRow(work_date="2026-07-06", biometric_id="NORMAL", time_in="08:05", time_out="16:55"),
            AttendanceTemplateRow(work_date="2026-07-06", biometric_id="VARIANCE", time_in="09:00", time_out="17:00"),
            AttendanceTemplateRow(work_date="2026-07-06", biometric_id="ABSENT"),
            AttendanceTemplateRow(work_date="2026-07-06", biometric_id="REST", time_in="10:00", time_out="14:00"),
            AttendanceTemplateRow(work_date="2026-07-06", biometric_id="LEAVE"),
            AttendanceTemplateRow(work_date="2026-07-06", biometric_id="UNSCHEDULED"),
        ]
        preview = self.call_import(AttendanceTemplateImportPayload(dry_run=True, rows=rows))
        self.assertEqual(
            preview["summary"],
            {
                "rows": 6,
                "ready": 1,
                "needs_review": 3,
                "errors": 0,
                "skipped": 2,
                "manual_preserved": 0,
                "imported": 0,
            },
        )

        result = self.call_import(
            AttendanceTemplateImportPayload(
                dry_run=False,
                file_name="attendance-grid.csv",
                rows=rows,
            )
        )
        self.assertEqual(result["summary"]["imported"], 4)

        conn = get_conn(self.db_path)
        try:
            logs = fetchall(
                conn,
                """
                SELECT e.employee_code, tl.attendance_status, tl.review_reason, tl.is_absent
                FROM time_logs tl
                JOIN employees e ON e.id=tl.employee_id
                ORDER BY e.employee_code
                """,
            )
        finally:
            conn.close()
        by_code = {row["employee_code"]: row for row in logs}
        self.assertEqual(by_code["NORMAL"]["attendance_status"], "Approved")
        self.assertIn("Major schedule variance", by_code["VARIANCE"]["review_reason"])
        self.assertEqual(by_code["ABSENT"]["review_reason"], "Absent on scheduled day")
        self.assertEqual(by_code["ABSENT"]["is_absent"], 1)
        self.assertEqual(by_code["REST"]["review_reason"], "Present on rest day")
        self.assertNotIn("LEAVE", by_code)
        self.assertNotIn("UNSCHEDULED", by_code)

    def test_manual_attendance_is_preserved(self) -> None:
        conn = get_conn(self.db_path)
        try:
            stamp = now_iso()
            conn.execute(
                """
                INSERT INTO time_logs(
                    employee_id, work_date, actual_in, actual_out, source,
                    attendance_status, created_at, updated_at
                ) VALUES(?, '2026-06-16', '07:55', '17:10', 'manual',
                         'Approved', ?, ?)
                """,
                (self.employee_id, stamp, stamp),
            )
            conn.commit()
        finally:
            conn.close()

        result = self.call_import(
            AttendanceTemplateImportPayload(
                dry_run=False,
                rows=[
                    AttendanceTemplateRow(
                        work_date="2026-06-16",
                        biometric_id="BIO-1",
                        time_in="08:00",
                        time_out="17:00",
                    )
                ],
            )
        )
        self.assertEqual(result["summary"]["manual_preserved"], 1)
        self.assertEqual(result["summary"]["imported"], 0)

    def test_only_owner_can_import_attendance(self) -> None:
        with (
            patch("api.attendance_template_import.require_api_key"),
            patch(
                "api.attendance_template_import.current_user_from_token",
                return_value={"display_name": "General Manager", "role_key": "supervisor"},
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                require_attendance_importer(None, None)
        self.assertEqual(raised.exception.status_code, 403)

    def test_supervisor_decisions_close_review_items(self) -> None:
        conn = get_conn(self.db_path)
        try:
            for work_date in ("2026-07-06", "2026-07-07"):
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(
                        employee_id, shift_date, start_time, end_time,
                        position, department, break_minutes, source
                    ) VALUES(?, ?, '08:00', '17:00',
                             'Staff', 'Operations', 60, 'planned')
                    """,
                    (self.employee_id, work_date),
                )
            conn.commit()
        finally:
            conn.close()

        self.call_import(
            AttendanceTemplateImportPayload(
                dry_run=False,
                rows=[
                    AttendanceTemplateRow(work_date="2026-07-06", biometric_id="BIO-1"),
                    AttendanceTemplateRow(
                        work_date="2026-07-07",
                        biometric_id="BIO-1",
                        time_in="09:00",
                        time_out="17:00",
                    ),
                ],
            )
        )

        conn = get_conn(self.db_path)
        try:
            logs = fetchall(
                conn,
                "SELECT id, work_date FROM time_logs ORDER BY work_date",
            )
        finally:
            conn.close()
        self.decide(int(logs[0]["id"]), "Approved")
        self.decide(int(logs[1]["id"]), "Rejected")

        conn = get_conn(self.db_path)
        try:
            resolved = fetchall(
                conn,
                "SELECT work_date, attendance_status, absence_type FROM time_logs ORDER BY work_date",
            )
            open_items = fetchall(
                conn,
                attendance_exception_sql() + " ORDER BY tl.work_date",
                ("2026-07-06", "2026-07-07"),
            )
        finally:
            conn.close()
        self.assertEqual(
            resolved,
            [
                {
                    "work_date": "2026-07-06",
                    "attendance_status": "Approved",
                    "absence_type": "Unexcused Absence",
                },
                {
                    "work_date": "2026-07-07",
                    "attendance_status": "Rejected",
                    "absence_type": None,
                },
            ],
        )
        self.assertEqual(open_items, [])


if __name__ == "__main__":
    unittest.main()
