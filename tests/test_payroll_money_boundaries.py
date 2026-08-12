from __future__ import annotations

import unittest

from core.payroll_engine import compute_semi_monthly_withholding_tax


class PayrollMoneyBoundaryTests(unittest.TestCase):
    def test_withholding_tax_uses_half_up_centavo_rounding(self) -> None:
        # 10,417.10 is 0.10 above the first taxable threshold.
        # 0.10 × 15% = 0.015, which must become ₱0.02.
        self.assertEqual(
            compute_semi_monthly_withholding_tax(10417.10),
            0.02,
        )

    def test_withholding_tax_stays_zero_at_threshold(self) -> None:
        self.assertEqual(
            compute_semi_monthly_withholding_tax(10417.00),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
