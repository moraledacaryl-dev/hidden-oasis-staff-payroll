from __future__ import annotations

from datetime import date
from typing import Any, Callable, Mapping

from .db import get_setting
from .money import money
from .statutory_periods import calendar_month_segments
from .statutory_snapshots import previous_month_snapshot_totals


def _segment_target_fraction(segment: Any) -> float:
    """Return the cumulative semi-monthly target reached by this segment."""
    return 0.5 if segment.end.day <= 15 else 1.0


def apply_calendar_month_statutory(
    conn: Any,
    result: Any,
    emp: dict[str, Any],
    period_start: str,
    period_end: str,
    *,
    gross_by_month: Mapping[date, float],
    get_sss_share: Callable[[Any, float], tuple[float, float, float]],
) -> dict[date, dict[str, float]]:
    """Apply statutory contributions from exact calendar-month earnings.

    The returned mapping is the immutable per-month snapshot payload that the
    payroll draft persistence layer must store with the payroll item.  Prior
    month-to-date values come only from settled, non-superseded snapshots.
    """
    segments = calendar_month_segments(period_start, period_end)
    expected_months = {segment.month_start for segment in segments}
    if set(gross_by_month) != expected_months:
        raise ValueError("gross_by_month must contain exactly every calendar month in the payroll cutoff")

    allocated_gross = money(sum(float(value or 0) for value in gross_by_month.values()))
    if abs(allocated_gross - money(result.gross_pay)) > 0.005:
        raise ValueError("dated statutory gross must reconcile to payroll gross_pay")

    result.sss_ee = result.sss_er = result.sss_ec = 0.0
    result.philhealth_ee = result.philhealth_er = 0.0
    result.pagibig_ee = result.pagibig_er = 0.0
    snapshots: dict[date, dict[str, float]] = {}
    if allocated_gross <= 0.005:
        return {segment.month_start: {"gross_pay": 0.0} for segment in segments}

    employee_id = int(emp["id"])
    declared = float(emp.get("declared_monthly_base") or 0)
    ph_rate = float(get_setting(conn, "philhealth_rate", "0.05") or 0.05)
    ph_floor = float(get_setting(conn, "philhealth_floor", "10000") or 10000)
    ph_ceiling = float(get_setting(conn, "philhealth_ceiling", "100000") or 100000)
    ph_month_total = min(max(declared or ph_floor, ph_floor), ph_ceiling) * ph_rate
    ph_month_ee = ph_month_total / 2.0
    ph_month_er = ph_month_total / 2.0
    pi_rate = float(get_setting(conn, "pagibig_rate", "0.02") or 0.02)
    pi_er_rate = float(get_setting(conn, "pagibig_employer_rate", "0.02") or 0.02)
    pi_ceiling = float(get_setting(conn, "pagibig_ceiling", "10000") or 10000)
    pi_base = min(declared, pi_ceiling)
    pi_month_ee = pi_base * pi_rate
    pi_month_er = pi_base * pi_er_rate

    for segment in segments:
        current_gross = money(gross_by_month[segment.month_start])
        snap = {"gross_pay": current_gross, "sss_ee": 0.0, "sss_er": 0.0, "sss_ec": 0.0,
                "philhealth_ee": 0.0, "philhealth_er": 0.0, "pagibig_ee": 0.0, "pagibig_er": 0.0}
        snapshots[segment.month_start] = snap
        if current_gross <= 0.005:
            continue
        prev = previous_month_snapshot_totals(conn, employee_id, segment.month_start, segment.start)

        if int(emp.get("benefits_sss") or 0):
            target_ee, target_er, target_ec = get_sss_share(conn, prev["gross"] + current_gross)
            snap["sss_ee"] = money(max(0.0, target_ee - prev["sss"]))
            snap["sss_er"] = money(max(0.0, target_er - prev["sss_er"]))
            snap["sss_ec"] = money(max(0.0, target_ec - prev["sss_ec"]))

        fraction = _segment_target_fraction(segment)
        if int(emp.get("benefits_philhealth") or 0):
            snap["philhealth_ee"] = money(max(0.0, (ph_month_ee * fraction) - prev["philhealth"]))
            snap["philhealth_er"] = money(max(0.0, (ph_month_er * fraction) - prev["philhealth_er"]))
        if int(emp.get("benefits_pagibig") or 0):
            snap["pagibig_ee"] = money(max(0.0, (pi_month_ee * fraction) - prev["pagibig"]))
            snap["pagibig_er"] = money(max(0.0, (pi_month_er * fraction) - prev["pagibig_er"]))

    for field in ("sss_ee", "sss_er", "sss_ec", "philhealth_ee", "philhealth_er", "pagibig_ee", "pagibig_er"):
        setattr(result, field, money(sum(snapshot.get(field, 0.0) for snapshot in snapshots.values())))
    return snapshots
