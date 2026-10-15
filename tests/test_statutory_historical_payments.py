import unittest
from decimal import Decimal
from core.statutory_historical_payments import HistoricalPaymentCandidate, verified_remittance_amount

class HistoricalPaymentsTests(unittest.TestCase):
    def test_only_verified_government_payments_count_once(self):
        payments = [
            HistoricalPaymentCandidate("bank", "r1", "sss", "2026-10", Decimal("250"), True, True),
            HistoricalPaymentCandidate("bank", "r1", "sss", "2026-10", Decimal("250"), True, True),
            HistoricalPaymentCandidate("payroll", "p1", "sss", "2026-10", Decimal("100"), False, True),
            HistoricalPaymentCandidate("bank", "r2", "sss", "2026-10", Decimal("500"), True, False),
        ]
        self.assertEqual(verified_remittance_amount(payments), Decimal("250.00"))

    def test_invalid_program_is_rejected(self):
        with self.assertRaises(ValueError):
            verified_remittance_amount([
                HistoricalPaymentCandidate("bank", "r3", "unknown", "2026-10", Decimal("1"), True, True)
            ])

if __name__ == "__main__":
    unittest.main()
