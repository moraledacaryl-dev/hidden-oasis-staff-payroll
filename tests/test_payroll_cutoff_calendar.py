import unittest
from datetime import date, timedelta

from core.payroll_cutoff_calendar import cutoff_containing, cutoff_for_month
from api.payroll_drafts import _validate_semimonthly_period
from fastapi import HTTPException


class PayrollCutoffCalendarTests(unittest.TestCase):
    def test_end_of_month_only_rolls_to_next_first_cutoff(self):
        self.assertEqual(cutoff_for_month(2026, 10, 1), (date(2026, 9, 30), date(2026, 10, 14)))
        self.assertEqual(cutoff_for_month(2026, 10, 2), (date(2026, 10, 15), date(2026, 10, 30)))
        self.assertEqual(cutoff_for_month(2026, 11, 1), (date(2026, 10, 31), date(2026, 11, 14)))
        self.assertEqual(cutoff_for_month(2027, 3, 1), (date(2027, 2, 28), date(2027, 3, 14)))
        self.assertEqual(cutoff_for_month(2028, 3, 1), (date(2028, 2, 29), date(2028, 3, 14)))

    def test_every_day_has_exactly_one_cutoff(self):
        cursor = date(2026, 1, 1)
        end = date(2029, 1, 1)
        while cursor < end:
            start, stop = cutoff_containing(cursor)
            self.assertLessEqual(start, cursor)
            self.assertGreaterEqual(stop, cursor)
            cursor += timedelta(days=1)

    def test_draft_validation_uses_operational_cutoffs(self):
        _validate_semimonthly_period(date(2026, 9, 30), date(2026, 10, 14))
        _validate_semimonthly_period(date(2026, 10, 15), date(2026, 10, 30))
        _validate_semimonthly_period(date(2028, 2, 29), date(2028, 3, 14))
        with self.assertRaises(HTTPException):
            _validate_semimonthly_period(date(2026, 10, 1), date(2026, 10, 15))

    def test_invalid_half(self):
        with self.assertRaises(ValueError):
            cutoff_for_month(2026, 10, 3)


if __name__ == "__main__":
    unittest.main()
