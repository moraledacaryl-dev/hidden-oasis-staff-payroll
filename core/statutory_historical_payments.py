"""Read-only source-of-truth distinctions for statutory benefits.

Employee collections and paid payroll runs are not proof of remittance to
government agencies. Remittance imports must be explicitly verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class HistoricalPaymentCandidate:
    source: str
    source_id: str
    program: str
    contribution_month: str
    amount: Decimal
    is_government_remittance: bool
    verified: bool


def verified_remittance_amount(candidates: list[HistoricalPaymentCandidate]) -> Decimal:
    """Only unique, explicitly verified agency payments can offset liability."""
    seen: set[tuple[str, str]] = set()
    total = Decimal("0.00")
    for payment in candidates:
        if payment.program not in {"sss", "philhealth", "pagibig"}:
            raise ValueError("Unknown contribution program")
        key = (payment.source, payment.source_id)
        if key in seen:
            continue
        seen.add(key)
        if payment.is_government_remittance and payment.verified:
            if payment.amount <= 0:
                raise ValueError("Verified payment must be positive")
            total += payment.amount
    return total.quantize(Decimal("0.01"))
