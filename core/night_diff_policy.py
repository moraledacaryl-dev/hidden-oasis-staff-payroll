from __future__ import annotations

from typing import Any

from core.db import fetchall, get_setting
from core.money import money
from core.schedule_source import trusted_schedule_rows


def apply_payable_night_diff(
    conn: Any,
    result: Any,
    employee: dict[str, Any],
    period_start: str,
    period_end: str,
) -> Any:
    """Rebuild night differential from payable attendance segments only.

    The base payroll engine historically measured the raw 22:00-06:00 overlap
    of an attendance log and then capped that number by total payable hours.
    That can award night differential for an unapproved late clock-out when the
    employee has enough payable daytime hours elsewhere in the same log.

    Hidden Oasis already has a canonical segment allocator for holiday/OT
    reconstruction. Reuse it here so ND is earned only on segments classified
    as payable regular work or payable OT. This also keeps split-shift,
    no-schedule, break, holiday/rest-day, and OT rules aligned in one place.
    """
    if str(employee.get("employment_type") or "").lower() == "freelance":
        return result

    # Import at execution time. core.__init__ installs the canonical holiday/OT
    # segment policy after the default payroll wrapper is registered, so by the
    # time payroll is calculated this resolves to the patched segment allocator.
    from core import holiday_payroll as holiday

    employee_id = int(employee["id"])
    hourly_rate = float(employee.get("hourly_rate") or 0)
    nd_rate = float(get_setting(conn, "night_diff_rate", "0.10") or 0.10)

    logs = fetchall(
        conn,
        """
        SELECT * FROM time_logs
        WHERE employee_id=? AND work_date BETWEEN ? AND ?
          AND attendance_status != 'Rejected'
        ORDER BY work_date, actual_in, id
        """,
        (employee_id, period_start, period_end),
    )
    schedules = trusted_schedule_rows(conn, period_start, period_end, employee_id)
    by_id = {
        int(schedule["scheduled_shift_id"]): schedule
        for schedule in schedules
        if schedule.get("scheduled_shift_id")
    }
    by_date: dict[str, list[dict[str, Any]]] = {}
    for schedule in schedules:
        by_date.setdefault(str(schedule["work_date"]), []).append(schedule)

    regular_allocated: dict[str, float] = {}
    segments: list[Any] = []
    for log in logs:
        if log.get("is_absent"):
            continue
        work_date = str(log["work_date"])
        shift_id = int(log.get("scheduled_shift_id") or 0)
        schedule = by_id.get(shift_id) if shift_id else None
        if not schedule and not shift_id:
            candidates = by_date.get(work_date, [])
            if len(candidates) == 1:
                schedule = candidates[0]
        segments.extend(
            holiday._log_segments(
                conn,
                employee,
                log,
                schedule,
                regular_allocated,
            )
        )

    new_hours = 0.0
    new_pay = 0.0
    new_nd_by_month = {}
    for segment in segments:
        nd_hours = float(holiday._night_paid_hours(segment) or 0)
        if nd_hours <= 0:
            continue
        multiplier, _label, _holiday_type = holiday.day_multiplier(
            conn,
            employee_id,
            segment.work_date,
            rest_work_date=segment.shift_work_date,
        )
        if segment.kind == "ot":
            pay_multiplier = holiday.overtime_multiplier(conn, multiplier)
        else:
            pay_multiplier = multiplier
        new_hours += nd_hours
        earned = nd_hours * hourly_rate * nd_rate * pay_multiplier
        new_pay += earned
        month = str(segment.shift_work_date or segment.work_date)[:7]
        new_nd_by_month[month] = new_nd_by_month.get(month, 0.0) + earned

    new_hours = round(new_hours, 4)
    new_pay = money(new_pay)
    old_hours = round(float(result.night_diff_hours or 0), 4)
    old_pay = money(float(result.night_diff_pay or 0))
    if old_hours == new_hours and old_pay == new_pay:
        return result

    dated = getattr(result, '_dated_gross_by_month', None)
    original = getattr(result, '_original_nd_by_month', None)
    if dated is not None and original is not None:
        from datetime import date
        adjusted = dict(dated)
        for month in set(original) | set(new_nd_by_month):
            key = date.fromisoformat(month + '-01')
            adjusted[key] = money(adjusted.get(key, 0) + new_nd_by_month.get(month, 0) - original.get(month, 0))
        # Reconcile only rounding residuals, never a material undated delta.
        target = money(result.gross_pay - old_pay + new_pay)
        residual = money(target - sum(money(v) for v in adjusted.values()))
        if abs(residual) > 0.05:
            raise ValueError('night differential monthly earnings did not reconcile')
        if residual:
            last = max(adjusted)
            adjusted[last] = money(adjusted[last] + residual)
        setattr(result, '_dated_gross_by_month', adjusted)
        setattr(result, '_original_nd_by_month', dict(new_nd_by_month))
    result.night_diff_hours = new_hours
    result.night_diff_pay = new_pay

    # ND is part of gross compensation, so any correction must flow through the
    # same statutory-contribution, cash-advance, deduction, and net-pay rebuild.
    from core.payroll_fractional_leave import _recompute_statutory_and_net

    _recompute_statutory_and_net(conn, result, employee, period_start, period_end)
    return result
