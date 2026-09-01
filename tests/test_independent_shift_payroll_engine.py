from __future__ import annotations

import unittest

from api.schedule_rest_days import ensure_schema as ensure_rest_day_schema
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import get_conn, init_db, now_iso
from core.payroll_engine import compute_payroll


class IndependentShiftPayrollEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        ensure_schedule_schema(self.conn)
        ensure_rest_day_schema(self.conn)
        self.conn.execute("DELETE FROM employees")
        stamp = now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO employees(
                employee_code,full_name,department,position,employment_type,status,
                hourly_rate,daily_rate,declared_monthly_base,standard_shift_hours,
                unpaid_break_minutes,security_no_break,benefits_sss,benefits_philhealth,
                benefits_pagibig,benefits_tax,created_at,updated_at
            ) VALUES('SPLIT-001','Split Shift Tester','Admin','Tester','Hourly','Active',
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
            (self.employee_id, day, start, end, 'Tester'),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_log(self, day: str, actual_in: str, actual_out: str, shift_id: int) -> None:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO time_logs(
                employee_id,work_date,actual_in,actual_out,source,verification_type,
                is_absent,approved_ot_hours,ot_status,attendance_status,
                scheduled_shift_id,created_at,updated_at
            ) VALUES(?,?,?,?, 'manual','Manual',0,0,'Approved','Reviewed',?,?,?)
            """,
            (self.employee_id, day, actual_in, actual_out, shift_id, stamp, stamp),
        )
        self.conn.commit()

    def result(self):
        rows = compute_payroll(self.conn, '2026-08-16', '2026-08-31')
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_two_distinct_eight_hour_shifts_are_sixteen_regular_hours(self) -> None:
        first = self.add_shift('2026-08-20', '05:00', '13:00')
        second = self.add_shift('2026-08-20', '13:00', '21:00')
        self.add_log('2026-08-20', '05:00', '13:00', first)
        self.add_log('2026-08-20', '13:00', '21:00', second)

        result = self.result()

        self.assertEqual(result.regular_hours, 16.0)
        self.assertEqual(result.approved_ot_hours, 0.0)
        self.assertEqual(result.regular_pay, 1600.0)
        self.assertEqual(result.ot_pay, 0.0)
        self.assertFalse(any('Inside-schedule hours beyond 8' in w for w in result.warnings or []))

    def test_true_excess_is_measured_per_shift_not_per_day(self) -> None:
        first = self.add_shift('2026-08-20', '05:00', '15:00')
        second = self.add_shift('2026-08-20', '15:00', '23:00')
        self.add_log('2026-08-20', '05:00', '15:00', first)
        self.add_log('2026-08-20', '15:00', '23:00', second)

        result = self.result()

        self.assertEqual(result.regular_hours, 16.0)
        self.assertEqual(result.approved_ot_hours, 2.0)
        self.assertEqual(result.regular_pay, 1600.0)
        self.assertEqual(result.ot_pay, 250.0)


if __name__ == '__main__':
    unittest.main()
