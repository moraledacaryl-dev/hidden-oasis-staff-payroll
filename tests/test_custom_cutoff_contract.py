from __future__ import annotations

import unittest
from pathlib import Path


class CustomCutoffContractTests(unittest.TestCase):
    def test_cutoff_page_accepts_explicit_dates(self) -> None:
        source = Path("apps/web/app/cutoff/page.tsx").read_text(encoding="utf-8")

        self.assertIn("start?: string; end?: string; payout?: string", source)
        self.assertIn("<CutoffDateSelector", source)
        self.assertIn("data-payout-date={payoutDate}", source)
        self.assertNotIn('name="half"', source)
        self.assertNotIn('name="month"', source)

    def test_date_selector_exposes_from_to_and_payment_date(self) -> None:
        source = Path("apps/web/components/CutoffDateSelector.tsx").read_text(encoding="utf-8")

        self.assertIn('name="start"', source)
        self.assertIn('name="end"', source)
        self.assertIn('name="payout"', source)
        self.assertIn("Payment date", source)

    def test_draft_uses_custom_cutoff_label(self) -> None:
        source = Path("apps/web/components/PayrollDraftButton.tsx").read_text(encoding="utf-8")

        self.assertIn('run_label: "Custom cutoff"', source)
        self.assertNotIn('run_label: "Semi-monthly"', source)

    def test_backend_keeps_semimonthly_guard_only_for_semimonthly_label(self) -> None:
        source = Path("api/payroll_drafts.py").read_text(encoding="utf-8")

        self.assertIn('if "semi-monthly" in label.lower():', source)
        self.assertIn("_validate_semimonthly_period(start_date, end_date)", source)
        self.assertIn("End date cannot be before start date.", source)
        self.assertIn("Payout date cannot be before the payroll period ends.", source)

    def test_saved_runs_show_coverage_and_payment_date(self) -> None:
        source = Path("apps/web/app/cutoff/page.tsx").read_text(encoding="utf-8")

        self.assertIn("<th>Coverage</th>", source)
        self.assertIn("<th>Payment date</th>", source)
        self.assertIn("run.period_start", source)
        self.assertIn("run.period_end", source)
        self.assertIn("run.payout_date", source)


if __name__ == "__main__":
    unittest.main()
