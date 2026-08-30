from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from api.holidays import HolidayPayload, _save
from api.schedule_rest_days import ensure_schema as ensure_rest_day_schema
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import fetchone, get_conn, init_db, now_iso
from core.holiday_payroll import day_multiplier, regular_holiday_eligibility
from core.payroll_engine import compute_payroll, save_payroll_draft
from core.payroll_fractional_leave import compute_payroll_with_fractional_leave


class HolidayCrudTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="holiday-api-", suffix=".sqlite", delete=False)
        self.path = handle.name
        handle.close()
        conn = get_conn(self.path)
        init_db(conn)
        conn.close()
        self.user = {"display_name": "Payroll Admin", "role_key": "payroll"}

    def tearDown(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    def test_regular_holiday_crud_and_duplicate_date(self) -> None:
        with patch("api.holidays.configured_db_path", return_value=self.path):
            created = _save(
                HolidayPayload(
                    holiday_date="2026-08-31",
                    name="National Heroes Day",
                    holiday_type="Regular Holiday",
                    active=True,
                ),
                None,
                self.user,
            )["item"]
            self.assertEqual(created["holiday_type"], "Regular Holiday")
            self.assertTrue(created["active"])
            with self.assertRaises(HTTPException) as caught:
                _save(
                    HolidayPayload(
                        holiday_date="2026-08-31",
                        name="Duplicate",
                        holiday_type="Special Non-Working Day",
                    ),
                    None,
                    self.user,
                )
            self.assertEqual(caught.exception.status_code, 409)

    def test_special_non_working_day_can_be_updated_and_deactivated(self) -> None:
        with patch("api.holidays.configured_db_path", return_value=self.path):
            created = _save(
                HolidayPayload(
                    holiday_date="2026-08-21",
                    name="Special Day",
                    holiday_type="Special Non-Working Day",
                    active=True,
                ),
                None,
                self.user,
            )["item"]
            updated = _save(
                HolidayPayload(
                    holiday_date="2026-08-21",
                    name="Special Day (Corrected)",
                    holiday_type="Special Non-Working Day",
                    active=False,
                ),
                int(created["id"]),
                self.user,
            )["item"]
            self.assertEqual(updated["name"], "Special Day (Corrected)")
            self.assertFalse(updated["active"])

    def test_api_rejects_free_form_holiday_types(self) -> None:
        with self.assertRaises(ValidationError):
            HolidayPayload(
                holiday_date="2026-08-31",
                name="Bad type",
                holiday_type="regular-ish",
            )


class HolidayPayrollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        ensure_schedule_schema(self.conn)
        ensure_rest_day_schema(self.conn)
        self.conn.execute("DELETE FROM employees")
        self.conn.execute("DELETE FROM holidays")
        self.conn.commit()
        self.employee_id = self.add_employee()

    def tearDown(self) -> None:
        self.conn.close()

    def add_employee(self, hourly_rate: float = 100.0) -> int:
        stamp = now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO employees(
                employee_code,full_name,department,position,employment_type,status,
                hourly_rate,daily_rate,declared_monthly_base,standard_shift_hours,
                unpaid_break_minutes,security_no_break,benefits_sss,benefits_philhealth,
                benefits_pagibig,benefits_tax,created_at,updated_at
            ) VALUES('HOL-001','Holiday Tester','Admin','Tester','Hourly','Active',
                ?,0,0,8,0,0,0,0,0,0,?,?)
            """,
            (hourly_rate, stamp, stamp),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_holiday(self, day: str, kind: str, *, active: bool = True, name: str = "Test Holiday") -> None:
        self.conn.execute(
            "INSERT INTO holidays(holiday_date,name,holiday_type,active,created_at) VALUES(?,?,?,?,?)",
            (day, name, kind, 1 if active else 0, now_iso()),
        )
        self.conn.commit()

    def add_shift(self, day: str, start: str, end: str, *, break_minutes: int = 0) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO scheduled_shifts(
                employee_id,shift_date,start_time,end_time,position,department,break_minutes,status,source
            ) VALUES(?,?,?,?,?,'Admin',?,'Approved','planned')
            """,
            (self.employee_id, day, start, end, "Tester", break_minutes),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_log(
        self,
        day: str,
        actual_in: str,
        actual_out: str,
        *,
        shift_id: int | None = None,
        approved_ot_hours: float = 0.0,
        is_absent: bool = False,
    ) -> int:
        stamp = now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO time_logs(
                employee_id,work_date,actual_in,actual_out,source,verification_type,
                is_absent,approved_ot_hours,ot_status,attendance_status,scheduled_shift_id,
                created_at,updated_at
            ) VALUES(?,?,?,?, 'manual','Manual',?,?, 'Approved','Reviewed',?,?,?)
            """,
            (
                self.employee_id,
                day,
                actual_in,
                actual_out,
                1 if is_absent else 0,
                approved_ot_hours,
                shift_id,
                stamp,
                stamp,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def mark_rest_day(self, day: str) -> None:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO schedule_day_markers(
                employee_id,work_date,marker_type,notes,active,created_by,created_at,updated_by,updated_at
            ) VALUES(?,?,'Rest Day','test',1,'test',?,'test',?)
            ON CONFLICT(employee_id,work_date,marker_type) DO UPDATE SET active=1,updated_at=excluded.updated_at
            """,
            (self.employee_id, day, stamp, stamp),
        )
        self.conn.commit()

    def add_preceding_workday(self, day: str) -> None:
        shift = self.add_shift(day, "08:00", "16:00")
        self.add_log(day, "08:00", "16:00", shift_id=shift)

    def result(self, start: str, end: str):
        rows = compute_payroll_with_fractional_leave(self.conn, start, end)
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_inactive_holiday_does_not_affect_payroll(self) -> None:
        self.add_holiday("2026-08-21", "Special Non-Working Day", active=False)
        shift = self.add_shift("2026-08-21", "08:00", "16:00")
        self.add_log("2026-08-21", "08:00", "16:00", shift_id=shift)
        result = self.result("2026-08-16", "2026-08-31")
        self.assertEqual(result.regular_pay, 800.0)
        self.assertEqual(result.holiday_pay, 0.0)

    def test_special_holiday_affects_only_exact_calendar_date(self) -> None:
        self.add_holiday("2026-08-21", "Special Non-Working Day")
        ordinary = self.add_shift("2026-08-20", "08:00", "16:00")
        holiday = self.add_shift("2026-08-21", "08:00", "16:00")
        self.add_log("2026-08-20", "08:00", "16:00", shift_id=ordinary)
        self.add_log("2026-08-21", "08:00", "16:00", shift_id=holiday)
        result = self.result("2026-08-16", "2026-08-31")
        self.assertEqual(result.regular_pay, 1600.0)
        self.assertEqual(result.holiday_pay, 240.0)

    def test_special_holiday_plus_rest_day_uses_150_percent(self) -> None:
        self.add_holiday("2026-08-21", "Special Non-Working Day")
        self.mark_rest_day("2026-08-21")
        shift = self.add_shift("2026-08-21", "08:00", "16:00")
        self.add_log("2026-08-21", "08:00", "16:00", shift_id=shift)
        result = self.result("2026-08-16", "2026-08-31")
        self.assertEqual(result.regular_pay, 800.0)
        self.assertEqual(result.holiday_pay, 400.0)
        self.assertEqual(day_multiplier(self.conn, self.employee_id, "2026-08-21")[0], 1.5)

    def test_two_split_shifts_on_regular_holiday_remain_separate_but_share_one_day_guarantee(self) -> None:
        self.add_preceding_workday("2026-08-30")
        self.add_holiday("2026-08-31", "Regular Holiday")
        first = self.add_shift("2026-08-31", "08:00", "12:00")
        second = self.add_shift("2026-08-31", "16:00", "20:00")
        self.add_log("2026-08-31", "08:00", "12:00", shift_id=first)
        self.add_log("2026-08-31", "16:00", "20:00", shift_id=second)
        result = self.result("2026-08-16", "2026-08-31")
        self.assertEqual(result.regular_hours, 16.0)
        self.assertEqual(result.regular_pay, 1600.0)
        self.assertEqual(result.holiday_pay, 800.0)
        linked = self.conn.execute(
            "SELECT scheduled_shift_id FROM time_logs WHERE work_date='2026-08-31' ORDER BY actual_in"
        ).fetchall()
        self.assertEqual([int(row[0]) for row in linked], [first, second])

    def test_regular_holiday_plus_rest_day_split_shifts_reach_260_percent_without_duplicate_guarantee(self) -> None:
        self.add_preceding_workday("2026-08-30")
        self.add_holiday("2026-08-31", "Regular Holiday")
        self.mark_rest_day("2026-08-31")
        first = self.add_shift("2026-08-31", "08:00", "12:00")
        second = self.add_shift("2026-08-31", "16:00", "20:00")
        self.add_log("2026-08-31", "08:00", "12:00", shift_id=first)
        self.add_log("2026-08-31", "16:00", "20:00", shift_id=second)
        result = self.result("2026-08-16", "2026-08-31")
        self.assertEqual(result.holiday_pay, 1280.0)

    def test_unworked_regular_holiday_requires_preceding_workday_or_paid_leave_when_records_are_determinable(self) -> None:
        self.add_holiday("2026-08-31", "Regular Holiday")
        self.add_shift("2026-08-30", "08:00", "16:00")
        eligibility, reason = regular_holiday_eligibility(self.conn, self.employee_id, "2026-08-31")
        self.assertFalse(eligibility)
        self.assertIn("no approved paid leave", reason)
        result = self.result("2026-08-16", "2026-08-31")
        self.assertEqual(result.holiday_pay, 0.0)
        self.assertTrue(any("No unworked regular-holiday base pay" in warning for warning in result.warnings or []))

    def test_overnight_shift_applies_special_holiday_only_after_midnight(self) -> None:
        self.add_holiday("2026-08-31", "Special Non-Working Day")
        shift = self.add_shift("2026-08-30", "22:00", "06:00")
        self.add_log("2026-08-30", "22:00", "06:00", shift_id=shift)
        result = self.result("2026-08-16", "2026-08-31")
        self.assertEqual(result.holiday_pay, 180.0)
        self.assertEqual(result.night_diff_hours, 8.0)
        self.assertEqual(result.night_diff_pay, 98.0)

    def test_night_differential_on_regular_holiday_overtime_uses_ot_multiplier(self) -> None:
        self.add_preceding_workday("2026-08-30")
        self.add_holiday("2026-08-31", "Regular Holiday")
        shift = self.add_shift("2026-08-31", "14:00", "23:00")
        self.add_log("2026-08-31", "14:00", "23:00", shift_id=shift)
        result = self.result("2026-08-16", "2026-08-31")
        # The ninth hour (22:00-23:00) is both holiday OT and night work.
        self.assertEqual(result.approved_ot_hours, 1.0)
        self.assertEqual(result.ot_pay, 260.0)
        self.assertEqual(result.night_diff_hours, 1.0)
        self.assertEqual(result.night_diff_pay, 26.0)

    def test_saved_snapshot_is_not_rewritten_when_holiday_source_changes_and_new_calculation_sees_change(self) -> None:
        shift = self.add_shift("2026-08-21", "08:00", "16:00")
        self.add_log("2026-08-21", "08:00", "16:00", shift_id=shift)
        self.add_holiday("2026-08-21", "Special Non-Working Day")
        first = self.result("2026-08-16", "2026-08-31")
        run_id = save_payroll_draft(
            self.conn,
            "2026-08-16",
            "2026-08-31",
            "2026-09-01",
            "Holiday snapshot",
            "Payroll Admin",
            [first],
        )
        original = fetchone(
            self.conn,
            "SELECT holiday_pay,gross_pay FROM payroll_items WHERE payroll_run_id=? AND employee_id=?",
            (run_id, self.employee_id),
        )
        self.conn.execute(
            "UPDATE holidays SET holiday_type='Regular Holiday' WHERE holiday_date='2026-08-21'"
        )
        self.conn.commit()
        untouched = fetchone(
            self.conn,
            "SELECT holiday_pay,gross_pay FROM payroll_items WHERE payroll_run_id=? AND employee_id=?",
            (run_id, self.employee_id),
        )
        self.assertEqual(dict(original or {}), dict(untouched or {}))
        revised = self.result("2026-08-16", "2026-08-31")
        self.assertNotEqual(float(original["holiday_pay"]), revised.holiday_pay)

    def test_low_level_engine_keeps_shift_links_unambiguous_for_two_same_day_shifts(self) -> None:
        first = self.add_shift("2026-08-20", "08:00", "12:00")
        second = self.add_shift("2026-08-20", "16:00", "20:00")
        self.add_log("2026-08-20", "08:00", "12:00", shift_id=first)
        self.add_log("2026-08-20", "16:00", "20:00", shift_id=second)
        base = compute_payroll(self.conn, "2026-08-16", "2026-08-31")[0]
        self.assertEqual(base.regular_hours, 8.0)
        self.assertFalse(any("multiple shifts exist" in warning for warning in base.warnings or []))


if __name__ == "__main__":
    unittest.main()
