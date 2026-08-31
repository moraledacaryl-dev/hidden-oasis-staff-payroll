import unittest

from core.holiday_payroll import SPECIAL


class PayrollPreviewHolidayContractTests(unittest.TestCase):
    def test_special_non_working_day_label_is_stable_for_preview(self) -> None:
        self.assertEqual(SPECIAL, "Special Non-Working Day")


if __name__ == "__main__":
    unittest.main()
