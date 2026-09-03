from __future__ import annotations

import inspect
import unittest

import api.cash_advance_corrections as cash_corrections
import api.payroll_revision_workflow as payroll_revisions
from core.money import money


class FinalCentavoClosureTests(unittest.TestCase):
    def test_cash_correction_and_credit_settlement_use_half_up_money_policy(self) -> None:
        source = inspect.getsource(cash_corrections)
        self.assertNotIn("round(float(", source)
        self.assertIn("corrected = money(", source)
        self.assertIn("amount = money(", source)
        self.assertIn("new_credit = money(", source)
        self.assertEqual(money("1.005"), 1.01)
        self.assertEqual(money("2.675"), 2.68)

    def test_controlled_payroll_revision_uses_half_up_money_policy(self) -> None:
        source = inspect.getsource(payroll_revisions)
        self.assertNotIn("round(float(", source)
        self.assertIn("original_net = money(", source)
        self.assertIn("revised_net = money(", source)
        self.assertIn("difference = money(", source)
        self.assertEqual(money("3.335"), 3.34)


if __name__ == "__main__":
    unittest.main()
