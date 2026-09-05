from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from api.active_money_boundary_closure import install_active_money_boundary_closure


class ActiveMoneyBoundaryClosureTests(unittest.TestCase):
    def test_aggregate_adjustment_snapshot_preserves_half_up_centavos(self) -> None:
        import api.payroll_adjustments_aggregate as aggregate

        install_active_money_boundary_closure()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE payroll_item_adjustments (
                payroll_run_id INTEGER,
                employee_id INTEGER,
                additional_earning REAL,
                other_deduction REAL,
                cash_advance_amount REAL,
                version INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO payroll_item_adjustments VALUES (1, 7, 2.675, 3.335, 1.005, 4)"
        )
        row = aggregate.current_adjustment(conn, 1, 7, {"cash_advance_deduction": 0})
        self.assertEqual(row["additional_earning"], 2.68)
        self.assertEqual(row["other_deduction"], 3.34)
        self.assertEqual(row["cash_advance_amount"], 1.01)
        self.assertEqual(row["version"], 4)

    def test_fractional_leave_money_recompute_is_installed_without_native_centavo_rounding(self) -> None:
        import core.payroll_fractional_leave as fractional

        install_active_money_boundary_closure()
        self.assertEqual(
            fractional._recompute_statutory_and_net.__module__,
            "api.active_money_boundary_closure",
        )
        source = Path("api/active_money_boundary_closure.py").read_text(encoding="utf-8")
        self.assertIn("result.paid_leave_pay = corrected_pay", source)
        self.assertIn("result.net_pay = money(result.gross_pay - result.total_deductions)", source)
        self.assertNotIn("round(", source)
        review_source = Path("api/payroll_review_aggregate.py").read_text(encoding="utf-8")
        self.assertIn("install_active_money_boundary_closure()", review_source)


if __name__ == "__main__":
    unittest.main()
