from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.schedule_day_reset_safe import (
    ATTENDANCE_CLEARED_MARKER,
    ResetDayPayload,
    ensure_marker_schema,
    reset_day,
)
from core.db import get_conn, init_db, now_iso


class AttendanceClearTombstoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "staff.sqlite")
        conn = get_conn(self.db_path)
        init_db(conn)
        stamp = now_iso()
        conn.execute(
            """
            INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
            VALUES('EMP-CLEAR', 'Clear Test', 'Active', ?, ?)
            """,
            (stamp, stamp),
        )
        self.employee_id = int(conn.execute("SELECT id FROM employees WHERE employee_code='EMP-CLEAR'").fetchone()[0])
        conn.execute(
            """
            INSERT INTO time_logs(
                employee_id, work_date, actual_in, actual_out, source,
                verification_type, is_absent, approved_ot_hours,
                attendance_status, created_at, updated_at
            )
            VALUES(?, '2026-08-19', '21:00', '07:01', 'template_upload',
                   'Template Upload', 0, 0, 'Approved', ?, ?)
            """,
            (self.employee_id, stamp, stamp),
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_clear_day_deletes_old_attendance_and_persists_tombstone(self) -> None:
        payload = ResetDayPayload(
            employee_id=self.employee_id,
            work_date="2026-08-19",
            clear_reason="Employee did not work this rest day",
            confirmation="CLEAR DAY",
        )
        with (
            patch("api.schedule_day_reset_safe.DB_PATH", self.db_path),
            patch(
                "api.schedule_day_reset_safe.require_schedule_editor",
                return_value={"display_name": "Owner"},
            ),
        ):
            result = reset_day(payload, None, None)

        self.assertTrue(result["ok"])
        conn = get_conn(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM time_logs WHERE employee_id=? AND work_date='2026-08-19'",
                (self.employee_id,),
            ).fetchone()[0]
            self.assertEqual(count, 0)
            marker = conn.execute(
                """
                SELECT active, notes FROM schedule_day_markers
                WHERE employee_id=? AND work_date='2026-08-19' AND marker_type=?
                """,
                (self.employee_id, ATTENDANCE_CLEARED_MARKER),
            ).fetchone()
            self.assertIsNotNone(marker)
            self.assertEqual(int(marker[0]), 1)
            self.assertIn("did not work", str(marker[1]))
        finally:
            conn.close()

    def test_cleared_day_blocks_automated_reimport_but_allows_manual_actual(self) -> None:
        conn = get_conn(self.db_path)
        try:
            ensure_marker_schema(conn)
            conn.execute(
                """
                INSERT INTO schedule_day_markers(
                    employee_id, work_date, marker_type, notes, active, updated_by
                ) VALUES(?, '2026-08-19', ?, 'cleared', 1, 'Owner')
                """,
                (self.employee_id, ATTENDANCE_CLEARED_MARKER),
            )
            conn.execute(
                "DELETE FROM time_logs WHERE employee_id=? AND work_date='2026-08-19'",
                (self.employee_id,),
            )
            conn.execute(
                """
                INSERT INTO time_logs(
                    employee_id, work_date, actual_in, actual_out, source,
                    verification_type, is_absent, approved_ot_hours, attendance_status
                ) VALUES(?, '2026-08-19', '21:00', '07:01', 'template_upload',
                         'Template Upload', 0, 0, 'Approved')
                """,
                (self.employee_id,),
            )
            automated_count = conn.execute(
                "SELECT COUNT(*) FROM time_logs WHERE employee_id=? AND work_date='2026-08-19'",
                (self.employee_id,),
            ).fetchone()[0]
            self.assertEqual(automated_count, 0)

            conn.execute(
                """
                INSERT INTO time_logs(
                    employee_id, work_date, actual_in, actual_out, source,
                    verification_type, is_absent, approved_ot_hours, attendance_status
                ) VALUES(?, '2026-08-19', '08:00', '17:00', 'manual',
                         'Manual', 0, 0, 'Approved')
                """,
                (self.employee_id,),
            )
            manual = conn.execute(
                """
                SELECT actual_in, actual_out, source FROM time_logs
                WHERE employee_id=? AND work_date='2026-08-19'
                """,
                (self.employee_id,),
            ).fetchone()
            self.assertEqual(tuple(manual), ("08:00", "17:00", "manual"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
