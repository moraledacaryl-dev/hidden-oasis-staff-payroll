from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


CENTAVO = Decimal("0.01")


def decimal_value(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def money_decimal(value: Any) -> Decimal:
    """Quantize a monetary value to Philippine centavos."""
    return decimal_value(value).quantize(
        CENTAVO,
        rounding=ROUND_HALF_UP,
    )


def money(value: Any) -> float:
    """
    Canonical peso value for existing REAL/JSON contracts.

    Calculations are quantized with Decimal ROUND_HALF_UP before converting
    back to float for compatibility with the current database and API.
    """
    return float(money_decimal(value))


def money_or_zero(value: Any) -> float:
    """Tolerant integration-boundary variant for malformed external values."""
    try:
        return money(value)
    except (InvalidOperation, TypeError, ValueError):
        return 0.0
