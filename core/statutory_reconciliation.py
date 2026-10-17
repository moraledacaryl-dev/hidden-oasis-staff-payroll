"""Pure accounting arithmetic for statutory remittance reconciliation.

Employee payroll deductions are not agency remittances. This module keeps the
two separate and carries an accounting balance across contribution months.
A negative balance is an *unverified accounting credit*, not a government-
confirmed credit. All monetary inputs must be agency-specific.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


def _cent(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ContributionMonth:
    month: str
    employee_due: Decimal
    employer_due: Decimal
    remitted: Decimal


@dataclass(frozen=True)
class ReconciledMonth:
    month: str
    employee_due: Decimal
    employer_due: Decimal
    total_due: Decimal
    remitted: Decimal
    opening_balance: Decimal
    closing_balance: Decimal


def reconcile_months(
    months: Iterable[ContributionMonth],
    *,
    opening_balance: object = "0",
) -> list[ReconciledMonth]:
    """Positive closing balance is payable; negative is an accounting credit.

    Call separately for each government program. Months must be unique and
    chronologically ordered. Historical payments are included exactly once
    in the supplied remitted amount; this function does not infer payments
    from payroll status or employee outside-payment collections.
    """
    balance = _cent(opening_balance)
    results: list[ReconciledMonth] = []
    previous_month = ""
    for entry in months:
        if len(entry.month) != 7 or entry.month[4] != "-" or not entry.month[:4].isdigit() or not entry.month[5:].isdigit() or not 1 <= int(entry.month[5:]) <= 12:
            raise ValueError("month must be YYYY-MM")
        if entry.month <= previous_month:
            raise ValueError("contribution months must be strictly increasing")
        previous_month = entry.month
        employee = _cent(entry.employee_due)
        employer = _cent(entry.employer_due)
        remitted = _cent(entry.remitted)
        if min(employee, employer, remitted) < 0:
            raise ValueError("negative contributions or remittances require a separately audited adjustment")
        total = employee + employer
        closing = balance + total - remitted
        results.append(ReconciledMonth(entry.month, employee, employer, total, remitted, balance, closing))
        balance = closing
    return results
