from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from api.schedule_rest_days import ensure_schema as ensure_rest_days_schema
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import get_conn, init_db, now_iso
from core.quality import canonical_attendance_review_items


DAY = "2026-10-27"


class AttendanceRestDayReviewQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.conn = get_conn(Path(self.temporary.name) / "review.sqlite")
        init_db(self.conn)
        ensure_schedule_schema(self.conn)
        ensure_rest_days_schema(self.conn)
        stamp = now_iso()
        cursor = self.conn.execute(
            "INSERT INTO employees(employee_code, full_name, status, created_at, updated_at) VALUES('REST-QA', 'Test Staff', 'Active', ?, ?)",
            (stamp, stamp),
        )
        self.employee_id = int(cursor.lastrowid)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.temporary.cleanup()

    def mark_rest_day(self) -> None:
        self.conn.execute(
            """
            INSERT INTO schedule_day_markers(
                employee_id, work_date, marker_type, notes, active, created_at, updated_at
            ) VALUES (?, ?, 'Rest Day', '', 1, ?, ?)
            """,
            (self.employee_id, DAY, now_iso(), now_iso()),
        )
        self.conn.commit()

    def schedule_shift(self) -> None:
        self.conn.execute(
            "INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time) VALUES (?, ?, '08:00', '17:00')",
            (self.employee_id, DAY),
        )
        self.conn.commit()

    def log(
        self,
        *,
        status: str = "Needs Review",
        actual_in: str | None = None,
        actual_out: str | None = None,
        is_absent: int = 0,
        absence_type: str | None = None,
        notes: str = "Imported: no punches found",
        ot_status: str = "None",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO time_logs(
                employee_id, work_date, actual_in, actual_out,
                attendance_status, is_absent, absence_type, notes, ot_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.employee_id, DAY, actual_in, actual_out, status,
                is_absent, absence_type, notes, ot_status, now_iso(), now_iso(),
            ),
        )
        self.conn.commit()

    def review_items(self):
        return canonical_attendance_review_items(self.conn, DAY, DAY)

    def test_explicit_rest_day_empty_placeholder_is_not_reviewed(self) -> None:
        self.mark_rest_day()
        self.log()
        self.assertEqual(self.review_items(), [])

    def test_explicit_rest_day_false_absence_is_not_reviewed(self) -> None:
        self.mark_rest_day()
        self.log(is_absent=1, absence_type="Absent")
        self.assertEqual(self.review_items(), [])

    def test_legacy_rest_day_classification_is_not_reviewed(self) -> None:
        self.log(is_absent=1, absence_type="Rest Day")
        self.assertEqual(self.review_items(), [])

    def test_unscheduled_empty_note_only_placeholder_is_not_reviewed(self) -> None:
        self.log(notes="Imported data requires attendance validation")
        self.assertEqual(self.review_items(), [])

    def test_scheduled_missing_punch_remains_reviewable(self) -> None:
        self.schedule_shift()
        self.log()
        self.assertEqual(len(self.review_items()), 1)

    def test_rest_day_actual_punch_remains_reviewable(self) -> None:
        self.mark_rest_day()
        self.log(actual_in="09:00")
        self.assertEqual(len(self.review_items()), 1)

    def test_unscheduled_actual_punch_remains_reviewable(self) -> None:
        self.log(actual_out="17:00")
        self.assertEqual(len(self.review_items()), 1)

    def test_unscheduled_explicit_absence_remains_reviewable(self) -> None:
        self.log(is_absent=1, absence_type="Unexcused Absence")
        self.assertEqual(len(self.review_items()), 1)

    def test_pending_ot_remains_reviewable_on_rest_day(self) -> None:
        self.mark_rest_day()
        self.log(ot_status="Pending")
        self.assertEqual(len(self.review_items()), 1)

    def test_explicit_correction_with_note_remains_reviewable(self) -> None:
        self.log(status="Needs Correction", notes="Manager requested investigation")
        self.assertEqual(len(self.review_items()), 1)


if __name__ == "__main__":
    unittest.main()
