from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def to_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def covered_dates(start_date: str | date, end_date: str | date, period_start: str | date, period_end: str | date) -> list[str]:
    start = max(to_date(start_date), to_date(period_start))
    end = min(to_date(end_date), to_date(period_end))
    if end < start:
        return []
    cursor = start
    result: list[str] = []
    while cursor <= end:
        result.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return result


def paid_leave_days_for_cutoff(row: dict[str, Any], period_start: str | date, period_end: str | date, used_dates: set[str] | None = None) -> tuple[float, list[str]]:
    used_dates = used_dates or set()
    start = to_date(row["start_date"])
    end = to_date(row["end_date"])
    span = (end - start).days + 1
    if span <= 0:
        return 0.0, []
    dates = [item for item in covered_dates(start, end, period_start, period_end) if item not in used_dates]
    if not dates:
        return 0.0, []
    stored = float(row.get("days") or span)
    if span == 1:
        return round(max(0.0, min(stored, 1.0)), 4), dates
    return round(max(0.0, (stored / span) * len(dates)), 4), dates
