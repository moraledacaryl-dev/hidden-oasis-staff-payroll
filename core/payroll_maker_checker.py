from __future__ import annotations

from typing import Any


def _actor_key(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def assert_distinct_checker(run: dict[str, Any], actor: str) -> None:
    """Reject self-approval of a payroll run by its latest material maker."""
    maker = _actor_key(run.get("prepared_by"))
    checker = _actor_key(actor)
    if maker and checker and maker == checker:
        raise ValueError(
            "Maker-checker separation requires a different owner to approve this payroll run. "
            "Have a Payroll user prepare or materially edit the Draft before owner approval."
        )


def record_material_maker(conn: Any, run_id: int, actor: str, *, changed: bool) -> None:
    """Attribute a materially edited Draft to the actor who last changed its money."""
    if not changed:
        return
    conn.execute(
        "UPDATE payroll_runs SET prepared_by=? WHERE id=? AND status='Draft'",
        (str(actor).strip(), run_id),
    )
