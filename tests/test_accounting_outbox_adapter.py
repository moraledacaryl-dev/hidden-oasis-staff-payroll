from core.integration_outbox import (
    ACCOUNTING_FINANCIAL_ENDPOINT,
    ACCOUNTING_EMPLOYEE_ENDPOINT,
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


def test_accounting_endpoint_routes_identity_and_financial_events_separately():
    assert endpoint_for("accounting", "employee.sync") == ACCOUNTING_EMPLOYEE_ENDPOINT
    assert endpoint_for("accounting", "payroll.run.paid") == ACCOUNTING_FINANCIAL_ENDPOINT


def test_approved_payroll_becomes_reviewable_payable():
    result = canonical_accounting_payload(
        "payroll.run.approved",
        _envelope("payroll.run.approved", {"totals": {"net_pay": 12500}, "run": {"payment_date": "2026-07-31"}}),
    )
    assert result["source_app"] == "staff"
    assert result["financial_effect"] == "payable"
    assert result["amount"] == 12500
    assert result["proposed_links"]["supplier_name"] == "Employees"
    assert result["idempotency_key"] == "hidden_oasis_staff_payroll:payroll.run.approved:42:v1:1"


def test_paid_payroll_becomes_cash_out_for_daily_reconciliation():
    result = canonical_accounting_payload(
        "payroll.run.paid",
        _envelope("payroll.run.paid", {"totals": {"net_pay": 12000}, "run": {"payment_method": "bank_transfer"}}),
    )
    assert result["financial_effect"] == "cash_out"
    assert result["amount"] == 12000
    assert result["proposed_links"]["category"] == "Payroll"
    assert result["proposed_links"]["payment_method"] == "bank_transfer"


def test_cash_advance_release_and_repayment_have_opposite_cash_directions():
    released = canonical_accounting_payload(
        "cash_advance.released",
        _envelope("cash_advance.released", {"cash_advance": {"amount": 1500, "release_method": "cash"}}),
    )
    repaid = canonical_accounting_payload(
        "cash_advance.repaid",
        _envelope("cash_advance.repaid", {"repayment": {"amount": 500, "payment_method": "payroll_deduction"}}),
    )
    assert released["financial_effect"] == "cash_out"
    assert released["amount"] == 1500
    assert repaid["financial_effect"] == "cash_in"
    assert repaid["amount"] == 500


def test_13th_month_payment_is_cash_out():
    result = canonical_accounting_payload(
        "payroll.13th_month.paid",
        _envelope("payroll.13th_month.paid", {"run": {"net_13th_pay": 9000}}),
    )
    assert result["financial_effect"] == "cash_out"
    assert result["amount"] == 9000
    assert result["proposed_links"]["subcategory"] == "13th Month Pay"
