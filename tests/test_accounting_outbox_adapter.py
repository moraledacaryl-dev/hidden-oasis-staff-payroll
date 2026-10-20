import unittest

from core.integration_outbox import (
    ACCOUNTING_EMPLOYEE_ENDPOINT,
    ACCOUNTING_FINANCIAL_ENDPOINT,
    canonical_accounting_payload,
    endpoint_for,
)


def _envelope(event_type: str, payload: dict):
    return {
        "external_source": "hidden_oasis_staff_payroll",
        "external_id": f"{event_type}:42:v1",
        "event_type": event_type,
        "source_record_type": "PayrollRun",
        "source_record_id": 42,
        "source_revision": 1,
        "correlation_id": "payroll-run:42",
        "payload": payload,
    }


class AccountingOutboxAdapterTests(unittest.TestCase):
    def test_accounting_routes_identity_and_financial_events_separately(self):
        self.assertEqual(
            endpoint_for("accounting", "employee.sync"),
            ACCOUNTING_EMPLOYEE_ENDPOINT,
        )
        self.assertEqual(
            endpoint_for("accounting", "payroll.run.paid"),
            ACCOUNTING_FINANCIAL_ENDPOINT,
        )

    def test_approved_payroll_becomes_reviewable_payable(self):
        result = canonical_accounting_payload(
            "payroll.run.approved",
            _envelope(
                "payroll.run.approved",
                {
                    "totals": {"net_pay": 12500},
                    "run": {"payment_date": "2026-07-31"},
                },
            ),
        )
        self.assertEqual(result["source_app"], "staff")
        self.assertEqual(result["financial_effect"], "payable")
        self.assertEqual(result["amount"], 12500)
        self.assertEqual(result["proposed_links"]["supplier_name"], "Employees")
        self.assertEqual(
            result["idempotency_key"],
            "hidden_oasis_staff_payroll:payroll.run.approved:42:v1:1",
        )

    def test_paid_payroll_becomes_cash_out_for_daily_reconciliation(self):
        result = canonical_accounting_payload(
            "payroll.run.paid",
            _envelope(
                "payroll.run.paid",
                {
                    "totals": {"net_pay": 12000},
                    "run": {"payment_method": "bank_transfer"},
                },
            ),
        )
        self.assertEqual(result["financial_effect"], "cash_out")
        self.assertEqual(result["amount"], 12000)
        self.assertEqual(result["proposed_links"]["category"], "Payroll")
        self.assertEqual(
            result["proposed_links"]["payment_method"],
            "bank_transfer",
        )

    def test_paid_payroll_without_documented_method_does_not_assume_bank_transfer(self):
        result = canonical_accounting_payload(
            "payroll.run.paid",
            _envelope("payroll.run.paid", {"totals": {"net_pay": 12000}, "run": {}}),
        )
        self.assertEqual(result["financial_effect"], "cash_out")
        self.assertEqual(result["amount"], 12000)
        self.assertIsNone(result["proposed_links"]["payment_method"])

    def test_explicit_payroll_payment_method_is_preserved(self):
        for method in ("cash", "gcash", "bank_transfer"):
            with self.subTest(method=method):
                result = canonical_accounting_payload(
                    "payroll.run.paid",
                    _envelope(
                        "payroll.run.paid",
                        {"totals": {"net_pay": 12000}, "run": {"payment_method": method}},
                    ),
                )
                self.assertEqual(result["proposed_links"]["payment_method"], method)

    def test_thirteenth_month_without_method_remains_unspecified(self):
        result = canonical_accounting_payload(
            "payroll.13th_month.paid",
            _envelope("payroll.13th_month.paid", {"run": {"net_13th_pay": 9000}}),
        )
        self.assertIsNone(result["proposed_links"]["payment_method"])

    def test_cash_advance_release_is_real_cash_out(self):
        released = canonical_accounting_payload(
            "cash_advance.released",
            _envelope(
                "cash_advance.released",
                {"cash_advance": {"amount": 1500, "release_method": "cash"}},
            ),
        )
        self.assertEqual(released["financial_effect"], "cash_out")
        self.assertEqual(released["amount"], 1500)

    def test_payroll_deducted_repayment_does_not_create_fictitious_cash_in(self):
        for repayment in (
            {"amount": 500, "payment_method": "payroll_deduction", "payroll_run_id": 12},
            {"amount": 500, "method": "Payroll Deduction", "payroll_run_id": 12},
            {"amount": 500, "method": "salary deduction"},
            {"amount": 500},
        ):
            with self.subTest(repayment=repayment):
                result = canonical_accounting_payload(
                    "cash_advance.repaid",
                    _envelope("cash_advance.repaid", {"repayment": repayment}),
                )
                self.assertEqual(result["financial_effect"], "reference_only")
                self.assertEqual(result["amount"], 500)
                self.assertEqual(result["proposed_links"]["payment_method"], "payroll_deduction")
                self.assertEqual(result["proposed_links"]["settlement_source"], "payroll_deduction_non_cash")
                self.assertIsNone(result["proposed_journal"])

    def test_manual_cash_and_bank_repayments_are_cash_in(self):
        for payment_method in ("Cash", "GCash", "Bank Transfer"):
            with self.subTest(payment_method=payment_method):
                result = canonical_accounting_payload(
                    "cash_advance.repaid",
                    _envelope(
                        "cash_advance.repaid",
                        {"repayment": {"amount": 500, "payment_method": payment_method}},
                    ),
                )
                self.assertEqual(result["financial_effect"], "cash_in")
                self.assertEqual(result["amount"], 500)
                self.assertEqual(result["proposed_links"]["payment_method"], payment_method)

    def test_13th_month_payment_is_cash_out(self):
        result = canonical_accounting_payload(
            "payroll.13th_month.paid",
            _envelope(
                "payroll.13th_month.paid",
                {"run": {"net_13th_pay": 9000}},
            ),
        )
        self.assertEqual(result["financial_effect"], "cash_out")
        self.assertEqual(result["amount"], 9000)
        self.assertEqual(
            result["proposed_links"]["subcategory"],
            "13th Month Pay",
        )


if __name__ == "__main__":
    unittest.main()
