from __future__ import annotations

import unittest
from pathlib import Path


class PayrollCashAdvanceSuggestionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.editor = Path("apps/web/components/PayrollAdjustmentEditor.tsx").read_text(encoding="utf-8")
        cls.backend = Path("api/payroll_adjustments_aggregate.py").read_text(encoding="utf-8")

    def test_cash_advance_contract_keeps_aggregate_suggested_deduction(self) -> None:
        self.assertIn("deduction_per_payroll?: number | null", self.editor)
        self.assertIn("cash_advance_suggested", self.editor)
        self.assertIn("setCashSuggested(Number(data.cash_advance_suggested ?? 0))", self.editor)
        self.assertIn("def _suggested_total(advances: list[dict[str, Any]]) -> float:", self.backend)
        self.assertIn("total += min(available, scheduled)", self.backend)

    def test_editor_uses_total_balance_not_one_advance_balance(self) -> None:
        self.assertIn("cash_advance_total_available", self.editor)
        self.assertIn("max={cashTotalAvailable}", self.editor)
        self.assertIn("cash_advance_id: null", self.editor)
        self.assertNotIn("adjustment.cash_advance_amount || item.available_balance", self.editor)
        self.assertNotIn("item.available_balance || 0))", self.editor)

    def test_saved_zero_is_preserved(self) -> None:
        self.assertIn("Number(adjustment.cash_advance_amount ?? 0)", self.editor)
        self.assertIn("Number(current.cash_advance_amount ?? 0)", self.editor)
        self.assertNotIn("Number(current.cash_advance_amount || 0)", self.editor)

    def test_aggregate_suggestion_and_allocation_are_centavo_rounded_and_capped(self) -> None:
        self.assertIn("function roundMoney(value: number): number", self.editor)
        self.assertIn("const available = Math.max(0, roundMoney(Number(advance.available_balance ?? 0)))", self.editor)
        self.assertIn("const amount = Math.min(remaining, available);", self.editor)
        self.assertIn("remaining = roundMoney(remaining - amount);", self.editor)
        self.assertIn("available = round(max(0.0, float(advance.get(\"available_balance\") or 0)), 2)", self.backend)
        self.assertIn("return round(total, 2)", self.backend)


if __name__ == "__main__":
    unittest.main()
