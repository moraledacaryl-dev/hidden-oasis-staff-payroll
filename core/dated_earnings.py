from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

from .money import money
from .statutory_periods import calendar_month_segments


def _as_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass
class DatedEarningsLedger:
    """Accumulate payroll earnings by their actual earning date.

    This deliberately has no proportional allocation API.  Earnings with no
    defensible earning date must be resolved by the caller rather than spread
    across a cross-month cutoff.
    """

    period_start: date
    period_end: date
    _amounts: dict[date, float] = field(default_factory=dict)

    @classmethod
    def for_cutoff(cls, period_start: str | date, period_end: str | date) -> "DatedEarningsLedger":
        start = _as_date(period_start)
        end = _as_date(period_end)
        if end < start:
            raise ValueError("period_end must not be before period_start")
        return cls(start, end)

    def add(self, earning_date: str | date, amount: float) -> None:
        earned = _as_date(earning_date)
        if earned < self.period_start or earned > self.period_end:
            raise ValueError("earning date is outside payroll cutoff")
        value = float(amount or 0)
        if abs(value) < 0.000001:
            return
        self._amounts[earned] = self._amounts.get(earned, 0.0) + value

    def add_single_month_span(self, start: str | date, end: str | date, amount: float) -> None:
        """Attribute an aggregate earning only when its span is unambiguous.

        Weekly/manual source rows sometimes store an amount for a date range.
        If that range crosses a calendar month, there is no safe basis for
        inventing a split; the source must provide dated detail first.
        """
        span_start = max(_as_date(start), self.period_start)
        span_end = min(_as_date(end), self.period_end)
        if span_end < span_start:
            return
        if (span_start.year, span_start.month) != (span_end.year, span_end.month):
            raise ValueError("cross-month aggregate earning requires dated source detail")
        self.add(span_start, amount)

    def gross_by_month(self) -> Mapping[date, float]:
        segments = calendar_month_segments(self.period_start, self.period_end)
        totals = {segment.month_start: 0.0 for segment in segments}
        for earned, amount in self._amounts.items():
            month_start = earned.replace(day=1)
            totals[month_start] += amount
        return {month: money(amount) for month, amount in totals.items()}

    def reconcile(self, gross_pay: float) -> Mapping[date, float]:
        totals = dict(self.gross_by_month())
        target = money(gross_pay)
        delta = money(target - money(sum(totals.values())))
        if abs(delta) > 0.05:
            raise ValueError("dated earnings ledger must reconcile to payroll gross_pay")
        if abs(delta) >= 0.005:
            # Only absorb component-level centavo rounding drift.  Never use
            # this path to allocate substantive cross-month aggregate gross.
            if not self._amounts:
                raise ValueError("dated earnings ledger has no earning date for rounding residual")
            last_date = max(self._amounts)
            month_start = last_date.replace(day=1)
            totals[month_start] = money(totals[month_start] + delta)
        return totals
