from __future__ import annotations

import unittest
from pathlib import Path


class PayrollCashAdvanceSuggestionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = Path("apps/web/components/PayrollAdjustmentEditor.tsx").read_text(encoding="utf-8")

    def test_cash_advance_contract_keeps_suggested_deduction(self) -> None:
        self.assertIn("deduction_per_payroll?: number | null", self.source)
        self.assertIn("const suggested = Number(item.deduction_per_payroll ?? 0);", self.source)
        self.assertIn("saved ?? suggested", self.source)

    def test_new_selection_does_not_default_to_remaining_balance(self) -> None:
        self.assertNotIn("adjustment.cash_advance_amount || item.available_balance", self.source)
        self.assertNotIn("item.available_balance || 0))", self.source)

    def test_saved_zero_is_preserved(self) -> None:
        self.assertIn("Number(adjustment.cash_advance_amount ?? 0)", self.source)
        self.assertIn("Number(current.cash_advance_amount ?? 0)", self.source)
        self.assertNotIn("Number(current.cash_advance_amount || 0)", self.source)

    def test_suggestion_is_capped_and_rounded_to_centavos(self) -> None:
        self.assertIn("function roundMoney(value: number): number", self.source)
        self.assertIn("function clampCashAmount(advance: CashAdvance, value: number): number", self.source)
        self.assertIn("return Math.min(available, requested);", self.source)
        self.assertIn("setCashAmount(clampCashAmount(item, saved ?? suggested));", self.source)


if __name__ == "__main__":
    unittest.main()
