import unittest
from decimal import Decimal

from core.statutory_reconciliation import ContributionMonth, reconcile_months


class StatutoryReconciliationTests(unittest.TestCase):
    def test_underpayment_and_overpayment_carry_forward(self):
        rows = reconcile_months([
            ContributionMonth("2026-08", Decimal("1500"), Decimal("1500"), Decimal("2800")),
            ContributionMonth("2026-09", Decimal("1600"), Decimal("1600"), Decimal("3500")),
            ContributionMonth("2026-10", Decimal("1550"), Decimal("1550"), Decimal("2900")),
        ])
        self.assertEqual([r.closing_balance for r in rows], [Decimal("200.00"), Decimal("-100.00"), Decimal("100.00")])
        self.assertEqual(rows[1].opening_balance, Decimal("200.00"))

    def test_opening_balance_from_historical_reconciliation(self):
        rows = reconcile_months([ContributionMonth("2026-10", Decimal("100"), Decimal("100"), Decimal("50"))], opening_balance="300")
        self.assertEqual(rows[0].closing_balance, Decimal("450.00"))

    def test_no_implicit_payroll_remittance_or_double_counting(self):
        rows = reconcile_months([ContributionMonth("2026-10", Decimal("100"), Decimal("100"), Decimal("0"))])
        self.assertEqual(rows[0].closing_balance, Decimal("200.00"))

    def test_partial_remittances_accumulate_until_fully_settled(self):
        rows = reconcile_months([
            ContributionMonth("2026-08", Decimal("100"), Decimal("100"), Decimal("50")),
            ContributionMonth("2026-09", Decimal("100"), Decimal("100"), Decimal("125")),
            ContributionMonth("2026-10", Decimal("100"), Decimal("100"), Decimal("425")),
        ])
        self.assertEqual(
            [row.closing_balance for row in rows],
            [Decimal("150.00"), Decimal("225.00"), Decimal("0.00")],
        )
        self.assertEqual(rows[2].opening_balance, Decimal("225.00"))

    def test_overpayment_credit_reduces_next_month_liability(self):
        rows = reconcile_months([
            ContributionMonth("2026-08", Decimal("100"), Decimal("100"), Decimal("350")),
            ContributionMonth("2026-09", Decimal("100"), Decimal("100"), Decimal("100")),
        ])
        self.assertEqual(rows[0].closing_balance, Decimal("-150.00"))
        self.assertEqual(rows[1].opening_balance, Decimal("-150.00"))
        self.assertEqual(rows[1].closing_balance, Decimal("-50.00"))

    def test_rejects_invalid_rows(self):
        cases = [
            [ContributionMonth("2026-10", Decimal("1"), Decimal("1"), Decimal("0")), ContributionMonth("2026-10", Decimal("1"), Decimal("1"), Decimal("0"))],
            [ContributionMonth("2026-13", Decimal("1"), Decimal("1"), Decimal("0"))],
            [ContributionMonth("2026-10", Decimal("-1"), Decimal("1"), Decimal("0"))],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    reconcile_months(entries)


if __name__ == "__main__":
    unittest.main()
