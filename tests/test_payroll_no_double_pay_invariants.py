from __future__ import annotations

import unittest

from api.schedule_rest_days import ensure_schema as ensure_rest_day_schema
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import get_conn, init_db, now_iso
from core.payroll_fractional_leave import compute_payroll_with_fractional_leave


class PayrollNoDoublePayInvariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        ensure_schedule_schema(self.conn)
        ensure_rest_day_schema(self.conn)
        self.conn.execute("DELETE FROM employees")
        self.conn.execute("DELETE FROM holidays")
        stamp = now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO employees(
                employee_code,full_name,department,position,employment_type,status,
                hourly_rate,daily_rate,declared_monthly_base,standard_shift_hours,
                unpaid_break_minutes,security_no_break,benefits_sss,benefits_philhealth,
                benefits_pagibig,benefits_tax,created_at,updated_at
            ) VALUES('INV-001','Invariant Tester','Admin','Staff','Hourly','Active',
                100,0,0,8,0,0,0,0,0,0,?,?)
            """,
            (stamp, stamp),
        )
        self.employee_id = int(cursor.lastrowid)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def add_shift(self, day: str, start: str, end: str) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO scheduled_shifts(
                employee_id,shift_date,start_time,end_time,position,department,
                break_minutes,status,source
            ) VALUES(?,?,?,?,?,'Admin',0,'Approved','planned')
            """,
            (self.employee_id, day, start, end, "Staff"),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_log(self, day: str, start: str, end: str, shift_id: int) -> None:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO time_logs(
                employee_id,work_date,actual_in,actual_out,source,verification_type,
                is_absent,approved_ot_hours,ot_status,attendance_status,scheduled_shift_id,
                created_at,updated_at
            ) VALUES(?,?,?,?, 'manual','Manual',0,0,'Approved','Reviewed',?,?,?)
            """,
            (self.employee_id, day, start, end, shift_id, stamp, stamp),
        )
        self.conn.commit()

    def test_regular_holiday_split_shifts_do_not_duplicate_regular_hours_or_pay(self) -> None:
        preceding = self.add_shift("2026-08-30", "08:00", "16:00")
        self.add_log("2026-08-30", "08:00", "16:00", preceding)
        self.conn.execute(
            "INSERT INTO holidays(holiday_date,name,holiday_type,active,created_at) VALUES(?,?,?,?,?)",
            ("2026-08-31", "Test Regular Holiday", "Regular Holiday", 1, now_iso()),
        )
        first = self.add_shift("2026-08-31", "08:00", "12:00")
        second = self.add_shift("2026-08-31", "16:00", "20:00")
        self.add_log("2026-08-31", "08:00", "12:00", first)
        self.add_log("2026-08-31", "16:00", "20:00", second)

        result = compute_payroll_with_fractional_leave(
            self.conn,
            "2026-08-31",
            "2026-08-31",
        )[0]

        # Eight actual paid hours across two linked shifts remain eight regular
        # hours. Regular-holiday compensation is a premium on those hours, not a
        # second copy of the regular-hour bucket.
        self.assertEqual(result.regular_hours, 8.0)
        self.assertEqual(result.regular_pay, 800.0)
        self.assertEqual(result.approved_ot_hours, 0.0)
        self.assertEqual(result.ot_pay, 0.0)
        self.assertEqual(result.holiday_pay, 800.0)
        self.assertEqual(result.gross_pay, 1600.0)

    def test_regular_plus_ot_never_exceeds_paid_worked_hours_on_ordinary_day(self) -> None:
        shift = self.add_shift("2026-08-20", "08:00", "17:00")
        self.add_log("2026-08-20", "08:00", "17:00", shift)
        result = compute_payroll_with_fractional_leave(
            self.conn,
            "2026-08-20",
            "2026-08-20",
        )[0]
        self.assertLessEqual(result.regular_hours + result.approved_ot_hours, 9.0)
        self.assertEqual(result.regular_hours, 8.0)
        self.assertEqual(result.approved_ot_hours, 1.0)
        self.assertEqual(result.regular_pay, 800.0)
        self.assertEqual(result.ot_pay, 125.0)


if __name__ == "__main__":
    unittest.main()
