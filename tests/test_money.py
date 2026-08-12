from __future__ import annotations

import unittest
from decimal import Decimal

from core.money import money, money_decimal, money_or_zero


class MoneyTests(unittest.TestCase):
    def test_half_cent_rounds_up(self) -> None:
        self.assertEqual(
            money_decimal("160.485"),
            Decimal("160.49"),
        )

    def test_negative_half_cent_rounds_away_from_zero(self) -> None:
        self.assertEqual(
            money_decimal("-160.485"),
            Decimal("-160.49"),
        )

    def test_fractional_cent_rounds_correctly(self) -> None:
        self.assertEqual(money("109.1875"), 109.19)

    def test_below_half_cent_rounds_down(self) -> None:
        self.assertEqual(money("12.804"), 12.80)

    def test_none_is_zero(self) -> None:
        self.assertEqual(money(None), 0.0)

    def test_tolerant_boundary_rejects_bad_value_as_zero(self) -> None:
        self.assertEqual(money_or_zero("not-money"), 0.0)


if __name__ == "__main__":
    unittest.main()
