from __future__ import annotations

import unittest
from pathlib import Path


class PayrollAdjustmentReadonlyCashContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Path("api/payroll_adjustments_aggregate.py").read_text(encoding="utf-8")

    def _between(self, start: str, end: str) -> str:
        start_at = self.source.index(start)
        end_at = self.source.index(end, start_at)
        return self.source[start_at:end_at]

    def test_adjustment_get_does_not_initialize_schema_or_persist_cash_balances(self) -> None:
        block = self._between(
            '@router.get("/payroll/runs/{run_id}/employees/{employee_id}/adjustments")',
            '@router.post("/payroll/runs/{run_id}/employees/{employee_id}/adjustments")',
        )
        self.assertNotIn("ensure_schema(conn)", block)
        self.assertNotIn("recalculate_balance", block)
        self.assertNotIn("conn.commit()", block)
        self.assertNotIn("persist_balances=True", block)

    def test_cash_preview_defaults_to_pure_balance_calculation(self) -> None:
        eligible = self._between("def _eligible_advances(", "def _other_draft_reserved_total(")
        snapshot = self._between("def _cash_snapshot(", '@router.get("/payroll/runs/')
        self.assertIn("persist_balances: bool = False", eligible)
        self.assertIn("calculate_balance", eligible)
        self.assertIn("recalculate_balance if persist_balances else calculate_balance", eligible)
        self.assertIn("persist_balances: bool = False", snapshot)
        self.assertIn("persist_balances=persist_balances", snapshot)

    def test_adjustment_post_preserves_intentional_write_behavior(self) -> None:
        post = self.source[self.source.index('@router.post("/payroll/runs/') :]
        self.assertIn("ensure_schema(conn)", post)
        self.assertGreaterEqual(post.count("persist_balances=True"), 2)
        self.assertIn("recalculate_balance(conn, advance_id)", post)
        self.assertIn("conn.commit()", post)

    def test_startup_owns_payroll_adjustment_schema(self) -> None:
        server = Path("api/server.py").read_text(encoding="utf-8")
        self.assertIn(
            "from api.payroll_adjustments import ensure_schema as ensure_payroll_adjustment_schema",
            server,
        )
        self.assertIn("ensure_payroll_adjustment_schema(conn)", server)


if __name__ == "__main__":
    unittest.main()
