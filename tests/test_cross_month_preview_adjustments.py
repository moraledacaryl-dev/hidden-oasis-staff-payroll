from datetime import date
import unittest

from core.db import now_iso
from core.payroll_engine import compute_payroll
from core.payroll_fractional_leave import compute_payroll_with_fractional_leave
from tests.test_preview_night_diff_pipeline import PreviewNightDiffPipelineTests as Fixtures


class CrossMonthPreviewAdjustmentTests(unittest.TestCase):
    setUp = Fixtures.setUp
    tearDown = Fixtures.tearDown
    add_shift = Fixtures.add_shift
    add_log = Fixtures.add_log

    def add_leave(self, start, end, days, *, entitled=False):
        leave_id = self.conn.execute(
            "INSERT INTO leave_types(name,paid) VALUES('Regression paid leave',1)"
        ).lastrowid
        self.conn.execute(
            "INSERT INTO leave_requests(employee_id,leave_type_id,start_date,end_date,days,status,created_at) VALUES(?,?,?,?,?,'Approved',?)",
            (self.employee_id, leave_id, start, end, days, now_iso()),
        )
        if entitled:
            self.conn.execute(
                "INSERT INTO employee_leave_entitlements(employee_id,leave_type_id,year,entitled,credits,used) VALUES(?,?,2026,1,20,0)",
                (self.employee_id, leave_id),
            )
        self.conn.commit()

    def preview(self):
        # Preview must never need a write transaction to repair its breakdown.
        self.conn.execute('PRAGMA query_only=ON')
        result = compute_payroll_with_fractional_leave(self.conn, '2026-09-30', '2026-10-14')[0]
        self.assertAlmostEqual(sum(result._dated_gross_by_month.values()), result.gross_pay, places=2)
        self.assertEqual(
            {month: values['gross_pay'] for month, values in result._statutory_snapshots.items()},
            result._dated_gross_by_month,
        )
        self.assertAlmostEqual(result.net_pay, result.gross_pay - result.total_deductions, places=2)
        return result

    def test_paid_leave_without_entitlement_is_allocated_to_leave_month(self):
        self.add_leave('2026-10-05', '2026-10-05', 1)
        result = self.preview()
        self.assertEqual(result.paid_leave_pay, 800)
        self.assertEqual(result._dated_gross_by_month, {date(2026, 9, 1): 0, date(2026, 10, 1): 800})

    def test_fractional_leave_removes_original_whole_days_in_both_months(self):
        self.add_leave('2026-09-30', '2026-10-01', 1, entitled=True)
        result = self.preview()
        self.assertEqual(result.paid_leave_days, 1)
        self.assertEqual(result._dated_gross_by_month, {date(2026, 9, 1): 400, date(2026, 10, 1): 400})

    def test_leave_clipped_to_cutoff_keeps_its_actual_dates(self):
        self.add_leave('2026-09-29', '2026-10-01', 1.5, entitled=True)
        self.assertEqual(self.preview()._dated_gross_by_month, {date(2026, 9, 1): 400, date(2026, 10, 1): 400})

    def test_rest_day_marker_adds_premium_to_correct_month(self):
        for day in ('2026-09-30', '2026-10-03'):
            shift = self.add_shift(day, '08:00', '16:00')
            self.add_log(day, '08:00', '16:00', shift)
        stamp = now_iso()
        self.conn.execute(
            "INSERT INTO schedule_day_markers(employee_id,work_date,marker_type,active,created_by,created_at,updated_by,updated_at) VALUES(?,'2026-10-03','Rest Day',1,'test',?,'test',?)",
            (self.employee_id, stamp, stamp),
        )
        self.conn.commit()
        result = self.preview()
        self.assertEqual(result.holiday_pay, 240)
        self.assertEqual(result._dated_gross_by_month, {date(2026, 9, 1): 800, date(2026, 10, 1): 1040})

    def test_ot_rounding_correction_reconciles_to_earning_month(self):
        self.conn.execute('UPDATE employees SET hourly_rate=62.5 WHERE id=?', (self.employee_id,))
        for day in ('2026-09-30', '2026-10-01'):
            shift = self.add_shift(day, '08:00', '18:00')
            self.add_log(day, '08:00', '17:01', shift)
        result = self.preview()
        self.assertEqual(result.ot_pay, 158.85)
        self.assertEqual(result.gross_pay, 1158.85)

    def test_split_shift_ot_and_holiday_replacement_does_not_double_count(self):
        for day in ('2026-09-30', '2026-10-01'):
            for start, end in (('06:00', '14:00'), ('15:00', '23:00')):
                shift = self.add_shift(day, start, end)
                self.add_log(day, start, end, shift)
        result = self.preview()
        self.assertEqual(result.regular_pay, 3200)
        self.assertEqual(result.ot_pay, 0)
        self.assertEqual(result.night_diff_pay, 20)
        self.assertEqual(result._dated_gross_by_month, {date(2026, 9, 1): 1610, date(2026, 10, 1): 1610})

    def test_missing_substantive_dated_detail_still_fails_closed(self):
        from core.payroll_fractional_leave import _recompute_statutory_and_net
        from core.db import fetchone
        shift = self.add_shift('2026-10-01', '08:00', '16:00')
        self.add_log('2026-10-01', '08:00', '16:00', shift)
        result = compute_payroll(self.conn, '2026-09-30', '2026-10-14')[0]
        result.other_earnings += 100
        emp = fetchone(self.conn, 'SELECT * FROM employees WHERE id=?', (self.employee_id,))
        with self.assertRaisesRegex(ValueError, 'requires dated earning detail'):
            _recompute_statutory_and_net(self.conn, result, emp, '2026-09-30', '2026-10-14')


if __name__ == '__main__':
    unittest.main()
