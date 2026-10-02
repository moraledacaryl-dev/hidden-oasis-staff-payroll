from __future__ import annotations

from typing import Any

from core.db import fetchone


PAID_LIKE_STATUSES = {"paid", "locked", "released"}


def is_paid_like_run(run: dict[str, Any] | None) -> bool:
    if not run:
        return False
    status = str(run.get("status") or "").strip().lower()
    return bool(run.get("paid_at")) or status in PAID_LIKE_STATUSES


def superseding_run_id(run: dict[str, Any] | None) -> int | None:
    if not run:
        return None
    value = run.get("superseded_by_run_id")
    if value in (None, "", 0, "0"):
        return None
    return int(value)


def assert_current_payroll_version(run: dict[str, Any]) -> None:
    superseded_by = superseding_run_id(run)
    if superseded_by:
        raise ValueError(
            f"Payroll run #{run.get('id')} is superseded by run #{superseded_by} and is audit history only."
        )


def revision_parent_for_payment(conn, run: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Validate revision ancestry before a final Paid transition.

    replace_unpaid is a pre-payment replacement: its parent must still be unpaid
    and must already point to this revision as the active version.

    adjust_paid is a post-payment correction: its parent must already represent
    a paid/finalized payroll and may only be superseded by this revision.
    """
    assert_current_payroll_version(run)

    parent_id = int(run.get("revision_of_run_id") or 0)
    if not parent_id:
        return None, None

    parent = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (parent_id,))
    if not parent:
        raise ValueError("Original payroll run for this revision no longer exists.")

    treatment = str(run.get("revision_treatment") or "").strip()
    parent_superseded_by = superseding_run_id(parent)
    run_id = int(run.get("id") or 0)

    if treatment == "replace_unpaid":
        if is_paid_like_run(parent):
            raise ValueError(
                "This replacement revision cannot be marked paid because its original payroll is already paid/finalized."
            )
        if parent_superseded_by != run_id:
            raise ValueError(
                "This replacement revision is not the active payroll version for the cutoff."
            )
        return parent, treatment

    if treatment == "adjust_paid":
        if not is_paid_like_run(parent):
            raise ValueError(
                "A paid adjustment revision can only supersede an already paid/finalized payroll run."
            )
        if parent_superseded_by not in (None, run_id):
            raise ValueError(
                f"Original payroll run is already superseded by run #{parent_superseded_by}."
            )
        return parent, treatment

    # Legacy revisions created before revision_treatment existed keep the safer
    # historical rule: they can only finalize against a paid parent.
    if not is_paid_like_run(parent):
        raise ValueError(
            "This payroll revision has no treatment and cannot be marked paid against an unpaid original."
        )
    if parent_superseded_by not in (None, run_id):
        raise ValueError(
            f"Original payroll run is already superseded by run #{parent_superseded_by}."
        )
    return parent, "adjust_paid"
