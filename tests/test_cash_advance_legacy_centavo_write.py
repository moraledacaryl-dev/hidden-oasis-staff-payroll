from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from api.cash_advances import _sync_legacy_fields


class CashAdvanceLegacyCentavoWriteTests(unittest.TestCase):
    def test_sync_legacy_fields_uses_half_up_centavos(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE cash_advances (
                id INTEGER PRIMARY KEY,
                amount REAL,
                deduction_per_payroll REAL,
                repayment_per_cutoff REAL,
                remaining_balance REAL,
                outstanding_balance REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO cash_advances(id,amount,deduction_per_payroll,repayment_per_cutoff,remaining_balance,outstanding_balance) VALUES(1,0,0,0,0,0)"
        )

        _sync_legacy_fields(conn, 1, 1.005, 2.675, 3.335)
        row = conn.execute(
            "SELECT amount,deduction_per_payroll,repayment_per_cutoff,remaining_balance,outstanding_balance FROM cash_advances WHERE id=1"
        ).fetchone()

        self.assertEqual(row, (1.01, 2.68, 2.68, 3.34, 3.34))

    def test_cash_advance_write_path_has_no_native_two_decimal_round(self) -> None:
        source = Path("api/cash_advances.py").read_text(encoding="utf-8")
        self.assertIn("from core.money import money", source)
        self.assertNotIn("round(float(", source)
        self.assertIn("values.append(money(value))", source)
        self.assertIn("stored_basis = money(", source)


if __name__ == "__main__":
    unittest.main()
