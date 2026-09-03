from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace

import api.payroll_adjustments_aggregate as aggregate_adjustments
import api.payroll_drafts as payroll_drafts
import api.payroll_recalculate as payroll_recalculate
import api.payroll_review_aggregate as aggregate_review
import core.cash_advance_payroll as cash_posting


class FinalMoneyLifecycleConsistencyTests(unittest.TestCase):
    def test_draft_recalculation_preserves_half_up_centavos(self) -> None:
        result = SimpleNamespace(
            full_name="Centavo Test",
            other_earnings=0.0,
            gross_pay=100.0,
            other_deductions=0.0,
            cash_advance_deduction=0.0,
            sss_ee=0.0,
            philhealth_ee=0.0,
            pagibig_ee=0.0,
            tax=0.0,
        )
        adjusted = payroll_recalculate._apply_manual(
            result,
            {
                "additional_earning": "1.005",
                "other_deduction": "2.675",
                "cash_advance_amount": "3.335",
            },
        )
        self.assertEqual(adjusted.other_earnings, 1.01)
        self.assertEqual(adjusted.gross_pay, 101.01)
        self.assertEqual(adjusted.other_deductions, 2.68)
        self.assertEqual(adjusted.cash_advance_deduction, 3.34)
        self.assertEqual(adjusted.total_deductions, 6.02)
        self.assertEqual(adjusted.net_pay, 94.99)

    def test_aggregate_fifo_preview_uses_half_up_centavos(self) -> None:
        advances = [
            {
                "id": 1,
                "live_balance": "10.005",
                "custom_next_deduction": "3.335",
            }
        ]
        available = aggregate_adjustments._available_after_other_drafts(advances, 0.0)
        self.assertEqual(available[0]["available_balance"], 10.01)
        self.assertEqual(aggregate_adjustments._suggested_total(available), 3.34)
        allocations = aggregate_adjustments._allocation_preview(available, 2.675)
        self.assertEqual(allocations[0]["amount"], 2.68)

    def test_authoritative_money_paths_do_not_use_native_round(self) -> None:
        modules = (
            payroll_drafts,
            payroll_recalculate,
            aggregate_adjustments,
            aggregate_review,
            cash_posting,
        )
        for module in modules:
            with self.subTest(module=module.__name__):
                self.assertNotIn("round(", inspect.getsource(module))


if __name__ == "__main__":
    unittest.main()
