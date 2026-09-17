from __future__ import annotations

from datetime import date
from typing import Any, Callable, Mapping

from .db import get_setting
from .money import money
from .statutory_history import month_previous_contribs
from .statutory_periods import calendar_month_segments


def apply_calendar_month_statutory(
    conn: Any,
    result: Any,
    emp: dict[str, Any],
    period_start: str,
    period_end: str,
    *,
    gross_by_month: Mapping[date, float],
    get_sss_share: Callable[[Any, float], tuple[float, float, float]],
) -> None:
    """Apply statutory contributions without inventing cross-month earnings.

    ``gross_by_month`` is deliberately required.  A cross-month cutoff must be
    backed by dated earnings; allocating aggregate gross by calendar-day ratio is
    financially unsafe and is therefore not supported here.
    """
    segments = calendar_month_segments(period_start, period_end)
    expected_months = {segment.month_start for segment in segments}
    supplied_months = set(gross_by_month)
    if supplied_months != expected_months:
        raise ValueError("gross_by_month must contain exactly every calendar month in the payroll cutoff")

    allocated_gross = money(sum(float(value or 0) for value in gross_by_month.values()))
    if abs(allocated_gross - money(result.gross_pay)) > 0.005:
        raise ValueError("dated statutory gross must reconcile to payroll gross_pay")

    result.sss_ee = result.sss_er = result.sss_ec = 0.0
    result.philhealth_ee = result.philhealth_er = 0.0
    result.pagibig_ee = result.pagibig_er = 0.0
    if allocated_gross <= 0.005:
        return

    employee_id = int(emp["id"])
    declared = float(emp.get("declared_monthly_base") or 0)
    ph_rate = float(get_setting(conn, "philhealth_rate", "0.05") or 0.05)
    ph_floor = float(get_setting(conn, "philhealth_floor", "10000") or 10000)
    ph_ceiling = float(get_setting(conn, "philhealth_ceiling", "100000") or 100000)
    ph_month_ee = min(max(declared or ph_floor, ph_floor), ph_ceiling) * ph_rate / 2.0
    pi_rate = float(get_setting(conn, "pagibig_rate", "0.02") or 0.02)
    pi_er_rate = float(get_setting(conn, "pagibig_employer_rate", "0.02") or 0.02)
    pi_ceiling = float(get_setting(conn, "pagibig_ceiling", "10000") or 10000)
    pi_base = min(declared, pi_ceiling)
    pi_month_ee = pi_base * pi_rate
    pi_month_er = pi_base * pi_er_rate

    for segment in segments:
        current_gross = money(gross_by_month[segment.month_start])
        if current_gross <= 0.005:
            continue
        prev = month_previous_contribs(conn, employee_id, segment.month_start, segment.start)

        if int(emp.get("benefits_sss") or 0):
            target_ee, target_er, target_ec = get_sss_share(conn, prev["gross"] + current_gross)
            result.sss_ee += max(0.0, target_ee - prev["sss"])
            result.sss_er += max(0.0, target_er - prev["sss_er"])
            result.sss_ec += max(0.0, target_ec - prev["sss_ec"])

        fraction = 1.0 if segment.end.day > 15 else 0.5
        if int(emp.get("benefits_philhealth") or 0):
            target = ph_month_ee * fraction
            result.philhealth_ee += max(0.0, target - prev["philhealth"])
            result.philhealth_er += max(0.0, target - prev["philhealth_er"])
        if int(emp.get("benefits_pagibig") or 0):
            result.pagibig_ee += max(0.0, (pi_month_ee * fraction) - prev["pagibig"])
            result.pagibig_er += max(0.0, (pi_month_er * fraction) - prev["pagibig_er"])

    for field in (
        "sss_ee", "sss_er", "sss_ec", "philhealth_ee", "philhealth_er",
        "pagibig_ee", "pagibig_er",
    ):
        setattr(result, field, money(getattr(result, field)))
