from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class StatutoryMonthSegment:
    """The portion of a payroll earning period that belongs to one calendar month."""

    month_start: date
    start: date
    end: date

    @property
    def month_end(self) -> date:
        return date(
            self.month_start.year,
            self.month_start.month,
            monthrange(self.month_start.year, self.month_start.month)[1],
        )

    @property
    def is_month_opening_segment(self) -> bool:
        return self.start == self.month_start

    @property
    def is_month_closing_segment(self) -> bool:
        return self.end == self.month_end


def _parse(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def calendar_month_segments(
    period_start: str | date,
    period_end: str | date,
) -> tuple[StatutoryMonthSegment, ...]:
    """Split an earning period at calendar-month boundaries, inclusively.

    Statutory contributions are calendar-month obligations. Payroll cutoffs are
    operational periods and may cross month-end (for example Aug 31-Sep 14), so
    callers must not classify the entire cutoff from only ``period_start`` or
    ``period_end``.
    """

    start = _parse(period_start)
    end = _parse(period_end)
    if end < start:
        raise ValueError("period_end must not be before period_start")

    segments: list[StatutoryMonthSegment] = []
    cursor = start
    while cursor <= end:
        month_start = cursor.replace(day=1)
        month_end = date(
            cursor.year,
            cursor.month,
            monthrange(cursor.year, cursor.month)[1],
        )
        segment_end = min(end, month_end)
        segments.append(
            StatutoryMonthSegment(
                month_start=month_start,
                start=cursor,
                end=segment_end,
            )
        )
        cursor = segment_end + timedelta(days=1)
    return tuple(segments)
