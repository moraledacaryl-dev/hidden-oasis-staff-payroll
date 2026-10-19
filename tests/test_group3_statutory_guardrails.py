from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from core.payroll_statutory import apply_calendar_month_statutory


class Group3StatutoryGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.emp = {
            "id": 12, "declared_monthly_base": 11476,
            "benefits_sss": 1, "benefits_philhealth": 1, "benefits_pagibig": 1,
        }
        self.settings = {
            "philhealth_rate": "0.05", "philhealth_floor": "10000",
            "philhealth_ceiling": "100000", "pagibig_rate": "0.02",
            "pagibig_employer_rate": "0.02", "pagibig_ceiling": "10000",
        }

    def calculate(self, start, end, gross, prior=None):
        result = SimpleNamespace(gross_pay=sum(gross.values()))
        prior = prior or {
            "gross": 0.0, "sss": 0.0, "sss_er": 0.0, "sss_ec": 0.0,
            "philhealth": 0.0, "philhealth_er": 0.0,
            "pagibig": 0.0, "pagibig_er": 0.0,
        }
        with patch("core.payroll_statutory.get_setting", side_effect=lambda _, key, default: self.settings.get(key, default)), \
             patch("core.payroll_statutory.previous_month_snapshot_totals", return_value=prior):
            snapshots = apply_calendar_month_statutory(
                None, result, self.emp, start, end, gross_by_month=gross,
                get_sss_share=lambda _, value: (300.0, 600.0, 30.0),
            )
        return result, snapshots

    def test_month_end_day_rolls_to_next_month_for_deductions(self):
        result, snapshots = self.calculate(
            "2026-09-30", "2026-10-14",
            {date(2026, 9, 1): 400.0, date(2026, 10, 1): 4600.0},
        )
        self.assertEqual(snapshots[date(2026, 9, 1)]["gross_pay"], 400.0)
        self.assertEqual(snapshots[date(2026, 9, 1)]["philhealth_ee"], 0.0)
        self.assertEqual(snapshots[date(2026, 10, 1)]["philhealth_ee"], 143.45)
        self.assertEqual(result.pagibig_ee, 100.0)
        self.assertEqual(result.sss_ee, 300.0)

    def test_second_half_deducts_only_remaining_contributions(self):
        prior = {
            "gross": 5000.0, "sss": 150.0, "sss_er": 300.0, "sss_ec": 15.0,
            "philhealth": 143.45, "philhealth_er": 143.45,
            "pagibig": 100.0, "pagibig_er": 100.0,
        }
        result, _ = self.calculate(
            "2026-10-15", "2026-10-30", {date(2026, 10, 1): 5000.0}, prior,
        )
        self.assertEqual(result.philhealth_ee, 143.45)
        self.assertEqual(result.pagibig_ee, 100.0)
        self.assertEqual(result.sss_ee, 150.0)

    def test_dated_gross_must_reconcile(self):
        with self.assertRaisesRegex(ValueError, "reconcile"):
            self.calculate(
                "2026-10-15", "2026-10-30",
                {date(2026, 10, 1): 5000.0, date(2026, 9, 1): 1.0},
            )

    def test_disabled_benefits_do_not_deduct(self):
        self.emp.update(benefits_sss=0, benefits_philhealth=0, benefits_pagibig=0)
        result, _ = self.calculate(
            "2026-10-15", "2026-10-30", {date(2026, 10, 1): 5000.0},
        )
        self.assertEqual((result.sss_ee, result.philhealth_ee, result.pagibig_ee), (0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
