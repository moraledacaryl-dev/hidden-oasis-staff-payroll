from decimal import Decimal

import pytest

from core.statutory_reconciliation import ContributionMonth, reconcile_months


def test_underpayment_and_overpayment_carry_forward():
    rows = reconcile_months([
        ContributionMonth("2026-08", Decimal("1500"), Decimal("1500"), Decimal("2800")),
        ContributionMonth("2026-09", Decimal("1600"), Decimal("1600"), Decimal("3500")),
        ContributionMonth("2026-10", Decimal("1550"), Decimal("1550"), Decimal("2900")),
    ])
    assert [r.closing_balance for r in rows] == [Decimal("200.00"), Decimal("-100.00"), Decimal("100.00")]
    assert rows[1].opening_balance == Decimal("200.00")


def test_opening_balance_from_historical_reconciliation():
    rows = reconcile_months([ContributionMonth("2026-10", Decimal("100"), Decimal("100"), Decimal("50"))], opening_balance="300")
    assert rows[0].closing_balance == Decimal("450.00")


def test_no_implicit_payroll_remittance_or_double_counting():
    rows = reconcile_months([ContributionMonth("2026-10", Decimal("100"), Decimal("100"), Decimal("0"))])
    assert rows[0].closing_balance == Decimal("200.00")


@pytest.mark.parametrize("entries", [
    [ContributionMonth("2026-10", Decimal("1"), Decimal("1"), Decimal("0")), ContributionMonth("2026-10", Decimal("1"), Decimal("1"), Decimal("0"))],
    [ContributionMonth("2026-13", Decimal("1"), Decimal("1"), Decimal("0"))],
    [ContributionMonth("2026-10", Decimal("-1"), Decimal("1"), Decimal("0"))],
])
def test_rejects_invalid_rows(entries):
    with pytest.raises(ValueError):
        reconcile_months(entries)
