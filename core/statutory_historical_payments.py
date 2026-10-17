"""Read-only source-of-truth distinctions for statutory benefits.

Employee collections and paid payroll runs are not proof of remittance to
government agencies. Remittance imports must be explicitly verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import date


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
    seen: set[tuple[str, str, str, str]] = set()
    total = Decimal("0.00")
    for payment in candidates:
        if payment.program not in {"sss", "philhealth", "pagibig"}:
            raise ValueError("Unknown contribution program")
        try:
            if date.fromisoformat(payment.contribution_month + "-01").strftime("%Y-%m") != payment.contribution_month:
                raise ValueError()
        except ValueError as exc:
            raise ValueError("Invalid contribution month") from exc
        if payment.is_government_remittance and payment.verified:
            if not payment.source or not payment.source_id:
                raise ValueError("Verified remittance requires traceable source identifiers")
            if not payment.amount.is_finite() or payment.amount <= 0:
                raise ValueError("Verified payment must be finite and positive")
            key = (payment.program, payment.contribution_month, payment.source, payment.source_id)
            if key in seen:
                continue
            seen.add(key)
            total += payment.amount
    return total.quantize(Decimal("0.01"))
