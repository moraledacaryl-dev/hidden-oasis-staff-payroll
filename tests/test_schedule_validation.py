from __future__ import annotations

import unittest

from fastapi import HTTPException

from api.schedule_validation import (
    validate_break_minutes,
    validate_day_editor_leave_fraction,
    validate_ot_hours,
    validate_time,
)


class ScheduleValidationTests(unittest.TestCase):
    def test_time_validation_accepts_hhmm_and_rejects_invalid(self):
        self.assertEqual(validate_time("09:30", "start_time"), "09:30")
        self.assertEqual(validate_time("23:59", "end_time"), "23:59")
        for value in ["9:30", "24:00", "12:60", "noon"]:
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    validate_time(value, "start_time")

    def test_break_and_ot_bounds(self):
        self.assertEqual(validate_break_minutes(60), 60)
        self.assertEqual(validate_ot_hours(2.5), 2.5)
        for value in [-1, 721]:
            with self.assertRaises(HTTPException):
                validate_break_minutes(value)
        for value in [-0.1, 25]:
            with self.assertRaises(HTTPException):
                validate_ot_hours(value)

    def test_leave_fraction_uses_days_or_hours(self):
        self.assertEqual(validate_day_editor_leave_fraction(0.5, None, 8), 0.5)
        self.assertEqual(validate_day_editor_leave_fraction(None, 4, 8), 0.5)
        self.assertEqual(validate_day_editor_leave_fraction(None, 3, 6), 0.5)
        for days in [0, -1, 1.5]:
            with self.assertRaises(HTTPException):
                validate_day_editor_leave_fraction(days, None, 8)


if __name__ == "__main__":
    unittest.main()
