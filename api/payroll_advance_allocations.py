"""Validated, persisted per-advance plans for draft payroll deductions.

These records are *plans*, not repayments. Only the authoritative Paid
transition in core.cash_advance_payroll posts them.
"""
from __future__ import annotations

import json
from typing import Any

from core.money import money, money_decimal


ALLOCATION_MODES = {"automatic", "manual"}


def read_allocations(row: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Read the canonical persisted plan; corrupt/manual plans fail closed."""
    if not row or str(row.get("cash_advance_allocation_mode") or "automatic") != "manual":
        return []
    raw = row.get("cash_advance_allocations_json")
    try:
        values = json.loads(str(raw or "[]"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Saved cash-advance allocations are invalid; review draft payroll before paying.") from exc
    if not isinstance(values, list):
        raise ValueError("Saved cash-advance allocations must be a list.")
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("A saved cash-advance allocation is invalid.")
        try:
            advance_id = int(value["cash_advance_id"])
            amount = money(value["amount"])
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError("A saved cash-advance allocation is invalid.") from exc
        if advance_id <= 0 or amount <= 0 or advance_id in seen:
            raise ValueError("Saved cash-advance allocations must have unique advance IDs and positive amounts.")
        seen.add(advance_id)
        result.append({"cash_advance_id": advance_id, "amount": amount})
    return sorted(result, key=lambda item: item["cash_advance_id"])


def encode_allocations(allocations: list[dict[str, Any]]) -> str:
    return json.dumps(allocations, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def allocation_total(allocations: list[dict[str, Any]]) -> float:
    return money(sum((money_decimal(item["amount"]) for item in allocations), start=money_decimal(0)))


def plan_description(mode: str, allocations: list[dict[str, Any]]) -> str:
    if mode != "manual":
        return "Automatic oldest-first"
    return "Specific advances: " + (", ".join(
        f"#{item['cash_advance_id']} ₱{item['amount']:,.2f}" for item in allocations
    ) if allocations else "none")
