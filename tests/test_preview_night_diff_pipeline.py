from __future__ import annotations

import unittest

from api.schedule_rest_days import ensure_schema as ensure_rest_day_schema
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import get_conn, init_db, now_iso
from core.payroll_fractional_leave import compute_payroll_with_fractional_leave


class PreviewNightDiffPipelineTests(unittest.TestCase):
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
            ) VALUES('PREVIEW-ND-001','Preview ND Tester','Admin','Tester','Hourly','Active',
                100,0,0,8,0,0,0,0,0,0,?,?)
            """,
            (stamp, stamp),
        )
        self.employee_id = int(cursor.lastrowid)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def add_shift(self, day: str, start: str, end: str, *, break_minutes: int = 0) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO scheduled_shifts(
                employee_id,shift_date,start_time,end_time,position,department,
                break_minutes,status,source
            ) VALUES(?,?,?,?,?,'Admin',?,'Approved','planned')
            """,
            (self.employee_id, day, start, end, 'Tester', break_minutes),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_log(
        self,
        day: str,
        actual_in: str,
        actual_out: str,
        shift_id: int | None,
        *,
        approved_ot_hours: float = 0.0,
    ) -> None:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO time_logs(
                employee_id,work_date,actual_in,actual_out,source,verification_type,
                is_absent,approved_ot_hours,ot_status,attendance_status,
                scheduled_shift_id,created_at,updated_at
            ) VALUES(?,?,?,?, 'manual','Manual',0,?,'Approved','Reviewed',?,?,?)
            """,
            (
                self.employee_id,
                day,
                actual_in,
                actual_out,
                approved_ot_hours,
                shift_id,
                stamp,
                stamp,
            ),
        )
        self.conn.commit()

    def preview_result(self):
        rows = compute_payroll_with_fractional_leave(self.conn, '2026-08-16', '2026-08-31')
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_preview_does_not_restore_nd_from_unapproved_late_clockout(self) -> None:
        shift = self.add_shift('2026-08-20', '13:00', '21:00')
        self.add_log('2026-08-20', '13:00', '22:30', shift, approved_ot_hours=0.0)

        result = self.preview_result()

        self.assertEqual(result.regular_hours, 8.0)
        self.assertEqual(result.approved_ot_hours, 0.0)
        self.assertEqual(result.night_diff_hours, 0.0)
        self.assertEqual(result.night_diff_pay, 0.0)

    def test_preview_only_counts_approved_night_ot(self) -> None:
        shift = self.add_shift('2026-08-20', '13:00', '21:00')
        self.add_log('2026-08-20', '13:00', '22:30', shift, approved_ot_hours=1.5)

        result = self.preview_result()

        self.assertEqual(result.regular_hours, 8.0)
        self.assertEqual(result.approved_ot_hours, 1.5)
        self.assertEqual(result.night_diff_hours, 0.5)
        self.assertEqual(result.night_diff_pay, 6.25)

    def test_early_clockin_does_not_steal_approved_post_shift_ot_into_nd(self) -> None:
        # Production-shaped case: 06:00-15:00 shift, employee clocks in at 05:44
        # and works approved OT after the shift. The scalar approved OT amount must
        # attach to the 15:00+ interval first, not the unapproved 05:44-06:00 time.
        shift = self.add_shift('2026-08-20', '06:00', '15:00', break_minutes=60)
        self.add_log('2026-08-20', '05:44', '18:24', shift, approved_ot_hours=2.25)

        result = self.preview_result()

        self.assertEqual(result.regular_hours, 8.0)
        self.assertEqual(result.approved_ot_hours, 2.25)
        self.assertEqual(result.night_diff_hours, 0.0)
        self.assertEqual(result.night_diff_pay, 0.0)


if __name__ == '__main__':
    unittest.main()
