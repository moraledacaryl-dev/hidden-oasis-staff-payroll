from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / "apps/web/components/PayrollAdjustmentEditor.tsx").read_text()
SERVER = (ROOT / "api/server.py").read_text()
AGGREGATE = (ROOT / "api/payroll_adjustments_aggregate.py").read_text()


class MultiCashAdvanceUiContractTests(unittest.TestCase):
    def test_editor_uses_employee_level_cash_advance_amount(self) -> None:
        self.assertNotIn("Select the exact advance", EDITOR)
        self.assertIn("automatically applied to eligible advances oldest first", EDITOR)
        self.assertIn('cash_advance_id: null', EDITOR)
        self.assertIn("cash_advance_total_available", EDITOR)
        self.assertIn("How this deduction will be applied", EDITOR)

    def test_server_routes_adjustments_to_aggregate_allocator(self) -> None:
        self.assertIn(
            "from api.payroll_adjustments_aggregate import router as payroll_adjustments_router",
            SERVER,
        )

    def test_aggregate_save_clears_legacy_exact_advance_binding(self) -> None:
        self.assertIn("cash_advance_id=NULL", AGGREGATE)
        self.assertIn("employee's available cash-advance balance", AGGREGATE)
        self.assertIn("_other_draft_reserved_total", AGGREGATE)


if __name__ == "__main__":
    unittest.main()
