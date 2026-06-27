from __future__ import annotations

import unittest

from core.payroll_leave_days import paid_leave_days_for_cutoff


class PayrollLeaveDaysTests(unittest.TestCase):
    def test_single_day_fractional_leave_uses_stored_days(self):
        row = {"start_date": "2026-07-01", "end_date": "2026-07-01", "days": 0.5}
        days, dates = paid_leave_days_for_cutoff(row, "2026-07-01", "2026-07-15")
        self.assertEqual(days, 0.5)
        self.assertEqual(dates, ["2026-07-01"])

    def test_multi_day_leave_is_prorated_to_cutoff_overlap(self):
        row = {"start_date": "2026-07-10", "end_date": "2026-07-20", "days": 11}
        days, dates = paid_leave_days_for_cutoff(row, "2026-07-01", "2026-07-15")
        self.assertEqual(days, 6.0)
        self.assertEqual(dates[0], "2026-07-10")
        self.assertEqual(dates[-1], "2026-07-15")

    def test_multi_day_fractional_total_is_distributed_over_span(self):
        row = {"start_date": "2026-07-01", "end_date": "2026-07-04", "days": 2}
        days, dates = paid_leave_days_for_cutoff(row, "2026-07-03", "2026-07-15")
        self.assertEqual(days, 1.0)
        self.assertEqual(dates, ["2026-07-03", "2026-07-04"])

    def test_already_used_dates_are_not_double_paid(self):
        row = {"start_date": "2026-07-01", "end_date": "2026-07-03", "days": 3}
        days, dates = paid_leave_days_for_cutoff(row, "2026-07-01", "2026-07-15", {"2026-07-01"})
        self.assertEqual(days, 2.0)
        self.assertEqual(dates, ["2026-07-02", "2026-07-03"])


if __name__ == "__main__":
    unittest.main()
