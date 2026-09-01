from __future__ import annotations

from typing import Any


def install() -> None:
    """Make independent scheduled-shift allocation the canonical payroll path.

    PR #54 added the correct per-shift policy but production callers continued
    importing ``core.payroll_engine.compute_payroll`` directly. Install one
    canonical wrapper here so drafts, previews, recalculation, legacy service
    paths, and tests all use the same policy exactly once.
    """
    from . import payroll_engine as engine
    from . import payroll_split_shift_policy as policy

    if getattr(engine.compute_payroll, "_default_per_shift_policy", False):
        return

    base_compute_payroll = engine.compute_payroll

    def compute_payroll(conn: Any, period_start: str, period_end: str) -> list[Any]:
        results = base_compute_payroll(conn, period_start, period_end)
        adjusted: list[Any] = []
        for result in results:
            employee = policy.fetchone(
                conn,
                "SELECT * FROM employees WHERE id=?",
                (int(result.employee_id),),
            )
            if (
                employee
                and str(employee.get("employment_type") or "").lower()
                != "freelance"
            ):
                result = policy.apply_independent_split_shift_allocation(
                    conn,
                    result,
                    employee,
                    period_start,
                    period_end,
                )
            adjusted.append(result)
        return adjusted

    compute_payroll._default_per_shift_policy = True  # type: ignore[attr-defined]

    # Every existing caller of core.payroll_engine.compute_payroll now receives
    # the same per-shift result. Keep the explicit policy entrypoint identical so
    # it cannot apply the correction a second time.
    engine.compute_payroll = compute_payroll
    policy.compute_payroll_per_shift = compute_payroll
