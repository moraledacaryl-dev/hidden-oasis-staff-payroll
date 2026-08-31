from __future__ import annotations

import unittest

from api.schedule_rest_days import ensure_schema as ensure_rest_day_schema
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import fetchone, get_conn, init_db, now_iso
from core.payroll_fractional_leave import compute_payroll_with_fractional_leave


class SpecialHolidayLeaveExclusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        ensure_schedule_schema(self.conn)
        ensure_rest_day_schema(self.conn)
        self.conn.execute("DELETE FROM employees")
        self.conn.execute("DELETE FROM holidays")
        self.conn.commit()

        stamp = now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO employees(
                employee_code,full_name,department,position,employment_type,status,
                hourly_rate,daily_rate,declared_monthly_base,standard_shift_hours,
                unpaid_break_minutes,security_no_break,benefits_sss,benefits_philhealth,
                benefits_pagibig,benefits_tax,created_at,updated_at
            ) VALUES('SPEC-LEAVE-001','Special Leave Tester','Admin','Tester','Hourly','Active',
                100,0,0,8,0,0,0,0,0,0,?,?)
            """,
            (stamp, stamp),
        )
        self.employee_id = int(cursor.lastrowid)
        self.conn.execute(
            "INSERT INTO holidays(holiday_date,name,holiday_type,active,created_at) VALUES('2026-08-21','Special Day','Special Non-Working Day',1,?)",
            (stamp,),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _add_paid_leave(self, leave_name: str) -> None:
        leave_type = fetchone(self.conn, "SELECT id FROM leave_types WHERE name=?", (leave_name,))
        self.assertIsNotNone(leave_type)
        self.conn.execute(
            """
            INSERT INTO leave_requests(
                employee_id,leave_type_id,start_date,end_date,days,paid,status,reason,created_at
            ) VALUES(?,?,'2026-08-21','2026-08-21',1,1,'Approved','test',?)
            """,
            (self.employee_id, int(leave_type["id"]), now_iso()),
        )
        self.conn.commit()

    def _result(self):
        rows = compute_payroll_with_fractional_leave(self.conn, "2026-08-16", "2026-08-31")
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_special_non_working_day_does_not_premium_service_incentive_leave(self) -> None:
        self._add_paid_leave("Service Incentive Leave")
        result = self._result()
        self.assertEqual(result.holiday_pay, 0.0)
        self.assertEqual(result.paid_leave_days, 1.0)
        self.assertEqual(result.paid_leave_pay, 800.0)

    def test_special_non_working_day_does_not_premium_sick_leave(self) -> None:
        self._add_paid_leave("Sick Leave")
        result = self._result()
        self.assertEqual(result.holiday_pay, 0.0)
        self.assertEqual(result.paid_leave_days, 1.0)
        self.assertEqual(result.paid_leave_pay, 800.0)

    def test_special_non_working_day_premium_applies_when_employee_physically_works(self) -> None:
        shift = self.conn.execute(
            """
            INSERT INTO scheduled_shifts(
                employee_id,shift_date,start_time,end_time,position,department,break_minutes,status,source
            ) VALUES(?,'2026-08-21','08:00','16:00','Tester','Admin',0,'Approved','planned')
            """,
            (self.employee_id,),
        ).lastrowid
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO time_logs(
                employee_id,work_date,actual_in,actual_out,source,verification_type,
                is_absent,approved_ot_hours,ot_status,attendance_status,scheduled_shift_id,
                created_at,updated_at
            ) VALUES(?,'2026-08-21','08:00','16:00','manual','Manual',0,0,'Approved','Reviewed',?,?,?)
            """,
            (self.employee_id, int(shift), stamp, stamp),
        )
        self.conn.commit()

        result = self._result()
        self.assertEqual(result.regular_pay, 800.0)
        self.assertEqual(result.holiday_pay, 240.0)


if __name__ == "__main__":
    unittest.main()
