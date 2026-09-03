from __future__ import annotations

import sqlite3
import unittest

from api.cash_advance_service import CashAdvancePayload, ensure_schema, recalculate_balance
from api.cash_repayments import ManualRepaymentPayload
from api.payroll_adjustments import AdjustmentPayload, to_centavos


class FinancialCentavoIngressTests(unittest.TestCase):
    def test_cash_advance_payload_uses_half_up_centavos(self) -> None:
        payload = CashAdvancePayload(
            employee_id=1,
            advance_date="2026-09-03",
            amount="1.005",
            deduction_per_payroll="2.675",
        )
        self.assertEqual(payload.amount, 1.01)
        self.assertEqual(payload.deduction_per_payroll, 2.68)

    def test_manual_repayment_payload_uses_half_up_centavos(self) -> None:
        payload = ManualRepaymentPayload(amount="1.005", repayment_date="2026-09-03")
        self.assertEqual(payload.amount, 1.01)

    def test_payroll_adjustment_payload_and_audit_centavos_match(self) -> None:
        payload = AdjustmentPayload(
            additional_earning="1.005",
            other_deduction="2.675",
            cash_advance_amount="3.335",
        )
        self.assertEqual(payload.additional_earning, 1.01)
        self.assertEqual(payload.other_deduction, 2.68)
        self.assertEqual(payload.cash_advance_amount, 3.34)
        self.assertEqual(to_centavos("1.005"), 101)
        self.assertEqual(to_centavos("2.675"), 268)

    def test_legacy_half_cent_cash_rows_reconcile_with_half_up_policy(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE payroll_runs (id INTEGER PRIMARY KEY, status TEXT)")
        ensure_schema(conn)
        advance_id = conn.execute(
            """
            INSERT INTO cash_advances(
                employee_id,advance_date,request_date,amount,repayment_method,
                deduction_per_payroll,repayment_per_cutoff,remaining_balance,
                outstanding_balance,ledger_opening_balance,status
            ) VALUES(1,'2026-09-03','2026-09-03',10.005,'Manual repayment',0,0,10.005,10.005,10.005,'Active')
            """
        ).lastrowid
        conn.execute(
            """
            INSERT INTO cash_advance_repayments(
                cash_advance_id,employee_id,repayment_date,payment_date,amount,
                source,payment_method,method,active
            ) VALUES(?,1,'2026-09-03','2026-09-03',1.005,'Manual','Cash','Cash',1)
            """,
            (advance_id,),
        )
        summary = recalculate_balance(conn, int(advance_id))
        self.assertEqual(summary["amount"], 10.01)
        self.assertEqual(summary["paid"], 1.01)
        self.assertEqual(summary["balance"], 9.0)


if __name__ == "__main__":
    unittest.main()
