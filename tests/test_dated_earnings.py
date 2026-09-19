from __future__ import annotations

import unittest
from datetime import date

from core.dated_earnings import DatedEarningsLedger


class DatedEarningsLedgerTests(unittest.TestCase):
    def test_aug31_sep14_uses_actual_earning_dates(self) -> None:
        ledger = DatedEarningsLedger.for_cutoff("2026-08-31", "2026-09-14")
        ledger.add("2026-08-31", 800.0)
        ledger.add("2026-09-01", 900.0)
        ledger.add("2026-09-14", 1000.0)
        self.assertEqual(
            ledger.reconcile(2700.0),
            {date(2026, 8, 1): 800.0, date(2026, 9, 1): 1900.0},
        )

    def test_sep30_oct14_uses_actual_earning_dates(self) -> None:
        ledger = DatedEarningsLedger.for_cutoff("2026-09-30", "2026-10-14")
        ledger.add("2026-09-30", 750.0)
        ledger.add("2026-10-01", 850.0)
        self.assertEqual(
            ledger.reconcile(1600.0),
            {date(2026, 9, 1): 750.0, date(2026, 10, 1): 850.0},
        )

    def test_cross_month_aggregate_is_rejected(self) -> None:
        ledger = DatedEarningsLedger.for_cutoff("2026-08-31", "2026-09-14")
        with self.assertRaisesRegex(ValueError, "requires dated source detail"):
            ledger.add_single_month_span("2026-08-31", "2026-09-06", 2000.0)

    def test_reconciliation_is_mandatory(self) -> None:
        ledger = DatedEarningsLedger.for_cutoff("2026-08-31", "2026-09-14")
        ledger.add("2026-08-31", 800.0)
        with self.assertRaisesRegex(ValueError, "must reconcile"):
            ledger.reconcile(900.0)

    def test_same_month_aggregate_is_allowed_without_inventing_cross_month_split(self) -> None:
        ledger = DatedEarningsLedger.for_cutoff("2026-09-01", "2026-09-14")
        ledger.add_single_month_span("2026-09-01", "2026-09-07", 1500.0)
        self.assertEqual(ledger.reconcile(1500.0), {date(2026, 9, 1): 1500.0})


if __name__ == "__main__":
    unittest.main()
