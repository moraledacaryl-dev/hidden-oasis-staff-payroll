from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PayrollStatutoryAllocationContractTests(unittest.TestCase):
    def test_cross_month_calculator_requires_dated_gross(self) -> None:
        source = (ROOT / "core" / "payroll_statutory.py").read_text(encoding="utf-8")
        self.assertIn("gross_by_month", source)
        self.assertIn("dated earnings", source)
        self.assertNotIn("total_days", source)
        self.assertNotIn("days /", source)

    def test_dated_gross_must_reconcile_to_payroll_gross(self) -> None:
        source = (ROOT / "core" / "payroll_statutory.py").read_text(encoding="utf-8")
        self.assertIn("must reconcile to payroll gross_pay", source)


if __name__ == "__main__":
    unittest.main()
