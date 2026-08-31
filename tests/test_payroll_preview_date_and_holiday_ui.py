from pathlib import Path
import unittest


class PayrollPreviewUiContractTests(unittest.TestCase):
    def test_preview_uses_editable_date_range_and_surfaces_holiday_pay(self) -> None:
        page = Path("apps/web/app/payroll/page.tsx").read_text()
        lines = Path("apps/web/components/PayrollEmployeeLines.tsx").read_text()

        self.assertIn('name="start" type="date"', page)
        self.assertIn('name="end" type="date"', page)
        self.assertIn("Holiday pay", page)
        self.assertIn("Active holidays in this preview", page)
        self.assertIn("holiday_pay?: number | null", lines)
        self.assertIn("<span>Holiday pay</span>", lines)


if __name__ == "__main__":
    unittest.main()
