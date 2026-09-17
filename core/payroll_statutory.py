from __future__ import annotations

from datetime import date
from typing import Any, Callable

from .db import get_setting
from .money import money
from .statutory_history import month_previous_contribs
from .statutory_periods import calendar_month_segments


def _month_gross_allocations(period_start: str, period_end: str, gross_pay: float) -> dict[date, float]:
    """Allocate aggregate cutoff gross across calendar segments deterministically.

    The payroll engine currently persists aggregate earning components. Until dated
    earning snapshots are persisted, allocate by inclusive earning days. This keeps
    calendar boundaries explicit and guarantees the allocation reconciles exactly
    to the cutoff gross. Same-month cutoffs are unchanged.
    """
    segments = calendar_month_segments(period_start, period_end)
    if not segments:
        return {}
    total_days = sum((segment.end - segment.start).days + 1 for segment in segments)
    remaining = money(gross_pay)
    allocations: dict[date, float] = {}
    for index, segment in enumerate(segments):
        if index == len(segments) - 1:
            amount = remaining
        else:
            days = (segment.end - segment.start).days + 1
            amount = money(float(gross_pay) * days / total_days)
            remaining = money(remaining - amount)
        allocations[segment.month_start] = amount
    return allocations


def apply_calendar_month_statutory(
    conn: Any,
    result: Any,
    emp: dict[str, Any],
    period_start: str,
    period_end: str,
    *,
    get_sss_share: Callable[[Any, float], tuple[float, float, float]],
) -> None:
    """Apply SSS, PhilHealth and Pag-IBIG per calendar month crossed by a cutoff."""
    result.sss_ee = result.sss_er = result.sss_ec = 0.0
    result.philhealth_ee = result.philhealth_er = 0.0
    result.pagibig_ee = result.pagibig_er = 0.0

    gross = money(result.gross_pay)
    if gross <= 0.005:
        return

    employee_id = int(emp["id"])
    declared = float(emp.get("declared_monthly_base") or 0)
    gross_by_month = _month_gross_allocations(period_start, period_end, gross)

    ph_rate = float(get_setting(conn, "philhealth_rate", "0.05") or 0.05)
    ph_floor = float(get_setting(conn, "philhealth_floor", "10000") or 10000)
    ph_ceiling = float(get_setting(conn, "philhealth_ceiling", "100000") or 100000)
    ph_month_total = min(max(declared, ph_floor), ph_ceiling) * ph_rate

    pi_rate = float(get_setting(conn, "pagibig_rate", "0.02") or 0.02)
    pi_er_rate = float(get_setting(conn, "pagibig_employer_rate", "0.02") or 0.02)
    pi_ceiling = float(get_setting(conn, "pagibig_ceiling", "10000") or 10000)
    pi_base = min(declared, pi_ceiling)
    pi_month_ee = pi_base * pi_rate
    pi_month_er = pi_base * pi_er_rate

    for segment in calendar_month_segments(period_start, period_end):
        current_gross = gross_by_month.get(segment.month_start, 0.0)
        if current_gross <= 0.005:
            continue
        prev = month_previous_contribs(conn, employee_id, segment.month_start, segment.start)

        if int(emp.get("benefits_sss") or 0):
            target_ee, target_er, target_ec = get_sss_share(conn, prev["gross"] + current_gross)
            result.sss_ee += max(0.0, target_ee - prev["sss"])
            result.sss_er += max(0.0, target_er - prev["sss_er"])
            result.sss_ec += max(0.0, target_ec - prev["sss_ec"])

        # Target-to-date is half the monthly employee/employer obligation through
        # day 15 and the full monthly obligation after day 15. A cross-month cutoff
        # therefore catches up the closing month and independently opens the next.
        full_month_due = segment.end.day > 15
        fraction = 1.0 if full_month_due else 0.5

        if int(emp.get("benefits_philhealth") or 0):
            target = ph_month_total * 0.5 * fraction
            result.philhealth_ee += max(0.0, target - prev["philhealth"])
            result.philhealth_er += max(0.0, target - prev["philhealth_er"])

        if int(emp.get("benefits_pagibig") or 0):
            result.pagibig_ee += max(0.0, (pi_month_ee * fraction) - prev["pagibig"])
            result.pagibig_er += max(0.0, (pi_month_er * fraction) - prev["pagibig_er"])

    result.sss_ee = money(result.sss_ee)
    result.sss_er = money(result.sss_er)
    result.sss_ec = money(result.sss_ec)
    result.philhealth_ee = money(result.philhealth_ee)
    result.philhealth_er = money(result.philhealth_er)
    result.pagibig_ee = money(result.pagibig_ee)
    result.pagibig_er = money(result.pagibig_er)
