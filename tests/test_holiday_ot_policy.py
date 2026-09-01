from __future__ import annotations

import unittest
from unittest.mock import patch

from core import holiday_payroll as holiday


class HolidayOtPolicyTests(unittest.TestCase):
    def _hours(self, segments, kind: str) -> float:
        return round(sum(float(seg.paid_hours) for seg in segments if seg.kind == kind), 4)

    @patch("core.holiday_payroll.get_setting", return_value="8")
    def test_split_shifts_each_receive_independent_regular_bucket(self, _setting):
        allocated: dict[str, float] = {}
        emp = {"unpaid_break_minutes": 0}

        first = holiday._log_segments(
            None,
            emp,
            {
                "work_date": "2026-08-17",
                "actual_in": "12:00",
                "actual_out": "21:00",
                "approved_ot_hours": 0,
                "is_absent": 0,
            },
            {
                "scheduled_shift_id": 1198,
                "shift_start": "12:00",
                "shift_end": "21:00",
                "break_minutes": 60,
            },
            allocated,
        )
        second = holiday._log_segments(
            None,
            emp,
            {
                "work_date": "2026-08-17",
                "actual_in": "21:00",
                "actual_out": "07:00",
                "approved_ot_hours": 0,
                "is_absent": 0,
            },
            {
                "scheduled_shift_id": 1298,
                "shift_start": "21:00",
                "shift_end": "07:00",
                "break_minutes": 0,
            },
            allocated,
        )

        segments = first + second
        self.assertEqual(self._hours(segments, "regular"), 16.0)
        self.assertEqual(self._hours(segments, "ot"), 2.0)
        self.assertEqual(allocated["shift:1198"], 8.0)
        self.assertEqual(allocated["shift:1298"], 8.0)

    @patch("core.holiday_payroll.get_setting", return_value="8")
    def test_unscheduled_excess_is_not_ot_without_approval(self, _setting):
        segments = holiday._log_segments(
            None,
            {"unpaid_break_minutes": 0},
            {
                "work_date": "2026-08-19",
                "actual_in": "21:00",
                "actual_out": "07:00",
                "approved_ot_hours": 0,
                "is_absent": 0,
            },
            None,
            {},
        )

        self.assertEqual(self._hours(segments, "regular"), 8.0)
        self.assertEqual(self._hours(segments, "ot"), 0.0)

    @patch("core.holiday_payroll.get_setting", return_value="8")
    def test_unscheduled_excess_can_be_explicitly_approved(self, _setting):
        segments = holiday._log_segments(
            None,
            {"unpaid_break_minutes": 0},
            {
                "work_date": "2026-08-19",
                "actual_in": "21:00",
                "actual_out": "07:00",
                "approved_ot_hours": 2,
                "is_absent": 0,
            },
            None,
            {},
        )

        self.assertEqual(self._hours(segments, "regular"), 8.0)
        self.assertEqual(self._hours(segments, "ot"), 2.0)


if __name__ == "__main__":
    unittest.main()
