from __future__ import annotations

import inspect
import unittest

import api.cash_advances as cash_advances
import api.server as server


class CashAdvanceListReadonlyContractTests(unittest.TestCase):
    def test_cash_advance_list_uses_pure_balance_calculation(self) -> None:
        source = inspect.getsource(cash_advances.list_cash_advances)
        self.assertIn("calculate_balance", source)
        self.assertNotIn("recalculate_balance", source)
        self.assertNotIn("ensure_schema", source)
        self.assertNotIn("commit(", source)
        self.assertNotIn("UPDATE ", source.upper())
        self.assertNotIn("ALTER TABLE", source.upper())
        self.assertNotIn("CREATE TABLE", source.upper())

    def test_write_paths_keep_persistent_recalculation(self) -> None:
        save_source = inspect.getsource(cash_advances.save_cash_advance)
        transition_source = inspect.getsource(cash_advances._transition_response)
        self.assertIn("recalculate_balance", save_source)
        self.assertIn("commit(", save_source)
        self.assertIn("recalculate_balance", transition_source)

    def test_startup_owns_cash_advance_compatibility_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_payroll_adjustment_schema(conn)", source)


if __name__ == "__main__":
    unittest.main()
