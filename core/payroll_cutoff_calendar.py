"""Inclusive payroll cutoffs with only the final calendar day carried forward.

The first cutoff starts on the preceding month's last day and ends on the
14th; the second starts on the 15th and ends on the day before month-end.
This is a scheduling rule, not a rewrite of historical paid payroll runs.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta


def cutoff_for_month(year: int, month: int, half: int) -> tuple[date, date]:
    if half not in (1, 2):
        raise ValueError("half must be 1 or 2")
    first = date(year, month, 1)
    if half == 1:
        return first - timedelta(days=1), date(year, month, 14)
    return date(year, month, 15), date(year, month, monthrange(year, month)[1] - 1)


def cutoff_containing(day: date) -> tuple[date, date]:
    """Return the operational cutoff for an attendance date."""
    if day.day == monthrange(day.year, day.month)[1]:
        following = day + timedelta(days=1)
        return cutoff_for_month(following.year, following.month, 1)
    return cutoff_for_month(day.year, day.month, 1 if day.day <= 14 else 2)
