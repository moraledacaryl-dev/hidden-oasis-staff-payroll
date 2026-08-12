from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import Mock, patch

from fastapi import HTTPException

from api.schedules import (
    DayActualPayload,
    DaySchedulePayload,
    ShiftPayload,
    create_shift,
    save_day_actual,
    save_day_schedule,
)


class ScheduleValidationRouteTests(unittest.TestCase):
    def assert_validation_error(self, callback) -> HTTPException:
        with self.assertRaises(HTTPException) as raised:
            callback()
        self.assertEqual(raised.exception.status_code, 422)
        return raised.exception

    def test_create_shift_rejects_non_positive_employee_id_before_persistence(self) -> None:
        error = self.assert_validation_error(
            lambda: create_shift(
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
            lambda: create_shift(
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

    def test_create_shift_persists_payload_notes_on_success(self) -> None:
        payload = ShiftPayload(
            employee_id=7,
            shift_date=date(2026, 7, 1),
            start_time="08:00",
            end_time="17:00",
            position="Receptionist",
            department="Front Office",
            break_minutes=60,
            notes="Front desk opener",
        )

        conn = Mock()
        cursor = Mock()
        cursor.lastrowid = 42
        conn.execute.return_value = cursor

        saved = {
            "id": 42,
            "employee_id": 7,
            "shift_date": "2026-07-01",
            "start_time": "08:00",
            "end_time": "17:00",
            "position": "Receptionist",
            "department": "Front Office",
            "break_minutes": 60,
            "notes": "Front desk opener",
        }

        with (
            patch(
                "api.schedules.require_schedule_editor",
                return_value={"display_name": "Owner"},
            ),
            patch("api.schedules.get_conn", return_value=conn),
            patch("api.schedules.ensure_schema"),
            patch("api.schedules.employee_exists", return_value=True),
            patch("api.schedules.fetch_leave", return_value=None),
            patch(
                "api.schedules.set_schedule_review_state",
                return_value={"issues": []},
            ),
            patch("api.schedules.schedule_row", return_value=saved),
            patch("api.schedules.log_schedule_change"),
        ):
            result = create_shift(payload)

        self.assertTrue(result["ok"])
        self.assertEqual(result["shift"]["notes"], "Front desk opener")
        self.assertEqual(result["shift"]["id"], 42)

        insert_params = conn.execute.call_args.args[1]
        self.assertEqual(insert_params[7], "Front desk opener")

        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_day_schedule_rejects_invalid_break_minutes_before_persistence(self) -> None:
        error = self.assert_validation_error(
            lambda: save_day_schedule(
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
            lambda: save_day_actual(
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
            lambda: save_day_actual(
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
