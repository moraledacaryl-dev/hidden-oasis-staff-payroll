from __future__ import annotations

from typing import Any


def _actor_key(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def assert_distinct_checker(conn: Any, run: dict[str, Any], actor: str) -> None:
    """Reject approval by anyone who materially prepared or edited the run.

    ``prepared_by`` covers draft creation and full recalculation. Append-only
    payroll adjustment events cover manual earning, deduction, and cash-advance
    edits without mutating historical maker attribution.
    """
    checker = _actor_key(actor)
    if not checker:
        raise ValueError("Payroll approval requires an attributed owner account.")

    if _actor_key(run.get("prepared_by")) == checker:
        raise ValueError(
            "Maker-checker separation requires a different owner to approve this payroll run. "
            "Have a Payroll user prepare or recalculate the Draft before owner approval."
        )

    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='payroll_adjustment_events'"
    ).fetchone()
    if not table_exists:
        return

    rows = conn.execute(
        "SELECT actor_name FROM payroll_adjustment_events WHERE payroll_run_id=?",
        (int(run["id"]),),
    ).fetchall()
    if any(_actor_key(row[0]) == checker for row in rows):
        raise ValueError(
            "Maker-checker separation prevents an owner who materially adjusted this Draft "
            "from approving it. Have a different owner approve the payroll run."
        )
