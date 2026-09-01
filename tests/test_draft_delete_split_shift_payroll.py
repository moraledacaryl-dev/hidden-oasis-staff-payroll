from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.payroll_recalculate import delete_draft
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import get_conn, init_db, now_iso
from core.payroll_split_shift_policy import compute_payroll_per_shift


class IndependentSplitShiftPayrollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        ensure_schedule_schema(self.conn)
        self.conn.execute("DELETE FROM employees")
        stamp = now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO employees(
                employee_code,full_name,department,position,employment_type,status,
                hourly_rate,daily_rate,declared_monthly_base,standard_shift_hours,
                unpaid_break_minutes,security_no_break,benefits_sss,benefits_philhealth,
                benefits_pagibig,benefits_tax,created_at,updated_at
            ) VALUES('SPLIT-001','Split Shift Tester','Operations','Staff','Hourly','Active',
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
            ) VALUES(?,?,?,?,?,'Operations',?,'Approved','planned')
            """,
            (self.employee_id, day, start, end, "Staff", break_minutes),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_log(
        self,
        day: str,
        actual_in: str,
        actual_out: str,
        shift_id: int,
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

    def test_two_eight_hour_same_day_scheduled_shifts_are_both_regular(self) -> None:
        first = self.add_shift("2026-08-20", "05:00", "13:00")
        second = self.add_shift("2026-08-20", "13:00", "21:00")
        self.add_log("2026-08-20", "05:00", "13:00", first)
        self.add_log("2026-08-20", "13:00", "21:00", second)

        result = compute_payroll_per_shift(self.conn, "2026-08-16", "2026-08-31")[0]

        self.assertEqual(result.regular_hours, 16.0)
        self.assertEqual(result.approved_ot_hours, 0.0)
        self.assertEqual(result.regular_pay, 1600.0)
        self.assertEqual(result.ot_pay, 0.0)
        self.assertFalse(any("beyond 8" in warning for warning in (result.warnings or [])))

    def test_longer_second_scheduled_shift_is_regular_not_auto_ot(self) -> None:
        first = self.add_shift("2026-08-20", "04:00", "13:00")
        second = self.add_shift("2026-08-20", "13:00", "21:00")
        self.add_log("2026-08-20", "04:00", "13:00", first)
        self.add_log("2026-08-20", "13:00", "21:00", second)

        result = compute_payroll_per_shift(self.conn, "2026-08-16", "2026-08-31")[0]

        self.assertEqual(result.regular_hours, 17.0)
        self.assertEqual(result.approved_ot_hours, 0.0)
        self.assertEqual(result.regular_pay, 1700.0)
        self.assertEqual(result.ot_pay, 0.0)
        self.assertFalse(any("beyond 8" in warning for warning in (result.warnings or [])))

    def test_monico_production_shape_is_seventeen_regular_zero_ot(self) -> None:
        first = self.add_shift("2026-08-17", "12:00", "21:00", break_minutes=60)
        second = self.add_shift("2026-08-17", "21:00", "07:00", break_minutes=60)
        self.add_log("2026-08-17", "11:57", "21:00", first)
        self.add_log("2026-08-17", "21:00", "07:01", second)

        result = compute_payroll_per_shift(self.conn, "2026-08-15", "2026-08-29")[0]

        self.assertEqual(result.regular_hours, 17.0)
        self.assertEqual(result.approved_ot_hours, 0.0)
        self.assertEqual(result.regular_pay, 1700.0)
        self.assertEqual(result.ot_pay, 0.0)
        self.assertFalse(any("beyond 8" in warning for warning in (result.warnings or [])))

    def test_only_approved_outside_schedule_time_is_ot_on_split_day(self) -> None:
        first = self.add_shift("2026-08-20", "05:00", "13:00")
        second = self.add_shift("2026-08-20", "13:00", "21:00")
        self.add_log("2026-08-20", "05:00", "13:00", first)
        self.add_log(
            "2026-08-20",
            "13:00",
            "22:00",
            second,
            approved_ot_hours=1.0,
        )

        result = compute_payroll_per_shift(self.conn, "2026-08-16", "2026-08-31")[0]

        self.assertEqual(result.regular_hours, 16.0)
        self.assertEqual(result.approved_ot_hours, 1.0)
        self.assertEqual(result.regular_pay, 1600.0)
        self.assertEqual(result.ot_pay, 125.0)


class DeleteDraftPayrollTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="delete-draft-", suffix=".sqlite", delete=False)
        self.path = handle.name
        handle.close()
        conn = get_conn(self.path)
        init_db(conn)
        stamp = now_iso()
        conn.execute(
            """
            INSERT INTO employees(employee_code,full_name,department,position,employment_type,status,
                hourly_rate,daily_rate,declared_monthly_base,standard_shift_hours,unpaid_break_minutes,
                security_no_break,benefits_sss,benefits_philhealth,benefits_pagibig,benefits_tax,created_at,updated_at)
            VALUES('DEL-001','Delete Tester','Admin','Staff','Hourly','Active',100,0,0,8,0,0,0,0,0,0,?,?)
            """,
            (stamp, stamp),
        )
        self.employee_id = int(conn.execute("SELECT id FROM employees WHERE employee_code='DEL-001'").fetchone()[0])
        cursor = conn.execute(
            """
            INSERT INTO payroll_runs(period_start,period_end,payout_date,run_label,status,prepared_by,created_at)
            VALUES('2026-08-16','2026-08-31','2026-09-01','Semi-monthly','Draft','Tester',?)
            """,
            (stamp,),
        )
        self.run_id = int(cursor.lastrowid)
        item_cursor = conn.execute(
            """
            INSERT INTO payroll_items(payroll_run_id,employee_id,regular_hours,regular_pay,gross_pay,total_deductions,net_pay,created_at)
            VALUES(?,?,8,800,800,0,800,?)
            """,
            (self.run_id, self.employee_id, stamp),
        )
        item_id = int(item_cursor.lastrowid)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payroll_item_adjustments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payroll_run_id INTEGER NOT NULL,
                payroll_item_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO payroll_item_adjustments(payroll_run_id,payroll_item_id,employee_id) VALUES(?,?,?)",
            (self.run_id, item_id, self.employee_id),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payroll_corrections(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payroll_run_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL,
                adjustment_type TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                apply_to_next_run INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'Recorded',
                applied_to_run_id INTEGER,
                applied_at TEXT
            )
            """
        )
        source = conn.execute(
            """
            INSERT INTO payroll_runs(period_start,period_end,payout_date,run_label,status,prepared_by,created_at)
            VALUES('2026-08-01','2026-08-15','2026-08-16','Semi-monthly','Approved','Tester',?)
            """,
            (stamp,),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO payroll_corrections(
                payroll_run_id,employee_id,adjustment_type,amount,reason,status,applied_to_run_id,applied_at
            ) VALUES(?,?,'Earning',100,'Correction','Applied',?,?)
            """,
            (source, self.employee_id, self.run_id, stamp),
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    def test_delete_draft_removes_owned_rows_and_restores_corrections(self) -> None:
        user = {"display_name": "Payroll Admin", "role_key": "payroll", "id": 1}
        with patch("api.payroll_recalculate.DB_PATH", self.path), patch(
            "api.payroll_recalculate.must_be_payroll_user", return_value=user
        ):
            result = delete_draft(self.run_id, None, None)
        self.assertTrue(result["ok"])

        conn = get_conn(self.path)
        try:
            self.assertIsNone(conn.execute("SELECT id FROM payroll_runs WHERE id=?", (self.run_id,)).fetchone())
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payroll_items WHERE payroll_run_id=?", (self.run_id,)).fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payroll_item_adjustments WHERE payroll_run_id=?", (self.run_id,)).fetchone()[0], 0)
            correction = conn.execute("SELECT status,applied_to_run_id,applied_at FROM payroll_corrections").fetchone()
            self.assertEqual(correction[0], "Recorded")
            self.assertIsNone(correction[1])
            self.assertIsNone(correction[2])
        finally:
            conn.close()

    def test_non_draft_run_cannot_be_deleted(self) -> None:
        conn = get_conn(self.path)
        conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=?", (self.run_id,))
        conn.commit()
        conn.close()
        user = {"display_name": "Payroll Admin", "role_key": "payroll", "id": 1}
        with patch("api.payroll_recalculate.DB_PATH", self.path), patch(
            "api.payroll_recalculate.must_be_payroll_user", return_value=user
        ):
            with self.assertRaises(HTTPException) as caught:
                delete_draft(self.run_id, None, None)
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
