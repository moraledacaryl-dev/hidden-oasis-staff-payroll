from __future__ import annotations

import unittest
from datetime import date

from fastapi import HTTPException

from api.schedule_input_validation_routes import (
    create_validated_shift,
    save_validated_day_actual,
    save_validated_day_schedule,
)
from api.schedules import DayActualPayload, DaySchedulePayload, ShiftPayload


class ScheduleValidationRouteTests(unittest.TestCase):
    def assert_validation_error(self, callback) -> HTTPException:
        with self.assertRaises(HTTPException) as raised:
            callback()
        self.assertEqual(raised.exception.status_code, 422)
        return raised.exception

    def test_create_shift_rejects_non_positive_employee_id_before_persistence(self) -> None:
        error = self.assert_validation_error(
            lambda: create_validated_shift(
                ShiftPayload(
                    employee_id=0,
                    shift_date=date(2026, 7, 1),
                    start_time="08:00",
                    end_time="17:00",
                    position="Receptionist",
                )
            )
        )
        self.assertIn("employee_id", str(error.detail))

    def test_create_shift_rejects_invalid_start_time_before_persistence(self) -> None:
        error = self.assert_validation_error(
            lambda: create_validated_shift(
                ShiftPayload(
                    employee_id=1,
                    shift_date=date(2026, 7, 1),
                    start_time="8am",
                    end_time="17:00",
                    position="Receptionist",
                )
            )
        )
        self.assertIn("start_time", str(error.detail))

    def test_day_schedule_rejects_invalid_break_minutes_before_persistence(self) -> None:
        error = self.assert_validation_error(
            lambda: save_validated_day_schedule(
                DaySchedulePayload(
                    employee_id=1,
                    shift_date=date(2026, 7, 1),
                    start_time="08:00",
                    end_time="17:00",
                    position="Receptionist",
                    break_minutes=721,
                )
            )
        )
        self.assertIn("break_minutes", str(error.detail))

    def test_day_actual_rejects_invalid_actual_time_before_persistence(self) -> None:
        error = self.assert_validation_error(
            lambda: save_validated_day_actual(
                DayActualPayload(
                    employee_id=1,
                    shift_date=date(2026, 7, 1),
                    actual_in="25:00",
                    actual_out="17:00",
                    approved_ot_hours=0,
                )
            )
        )
        self.assertIn("actual_in", str(error.detail))

    def test_day_actual_rejects_invalid_ot_hours_before_persistence(self) -> None:
        error = self.assert_validation_error(
            lambda: save_validated_day_actual(
                DayActualPayload(
                    employee_id=1,
                    shift_date=date(2026, 7, 1),
                    actual_in="08:00",
                    actual_out="17:00",
                    approved_ot_hours=25,
                )
            )
        )
        self.assertIn("approved_ot_hours", str(error.detail))


if __name__ == "__main__":
    unittest.main()
