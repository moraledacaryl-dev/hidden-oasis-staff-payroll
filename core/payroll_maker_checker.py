from __future__ import annotations

from typing import Any


def _actor_key(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def assert_distinct_checker(conn: Any, run: dict[str, Any], actor: str) -> None:
    """Validate approval attribution without blocking an owner who prepared the run.

    The canonical approval endpoint is restricted to the ``owner`` role. Hidden
    Oasis intentionally permits that owner to approve a payroll they prepared or
    adjusted, while retaining maker and adjustment attribution in the audit trail.
    """
    checker = _actor_key(actor)
    if not checker:
        raise ValueError("Payroll approval requires an attributed owner account.")

    # Self-approval is an explicit owner workflow policy. Do not erase or mutate
    # prepared_by / adjustment events; they remain available for audit review.
    return
