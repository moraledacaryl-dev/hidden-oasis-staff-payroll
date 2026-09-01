from __future__ import annotations

from typing import Any

from core.db import fetchall, fetchone, get_setting
from core.money import money
from core.payroll_engine import compute_overlap, day_pay_multipliers, overtime_multiplier
from core.schedule_source import trusted_schedule_rows


def _matched_schedule(
    log: dict[str, Any],
    by_id: dict[int, dict[str, Any]],
    by_date: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    shift_id = int(log.get("scheduled_shift_id") or 0)
    if shift_id:
        return by_id.get(shift_id)
    candidates = by_date.get(str(log.get("work_date") or ""), [])
    return candidates[0] if len(candidates) == 1 else None


def apply_independent_split_shift_allocation(
    conn: Any,
    result: Any,
    employee: dict[str, Any],
    period_start: str,
    period_end: str,
) -> Any:
    """Treat each explicitly scheduled same-day shift as independent regular time.

    Hidden Oasis rule: when an employee has two or more distinct scheduled
    shifts on one work date, paid work inside each scheduled window is regular
    time in full. The second shift is not converted to OT, and a scheduled shift
    longer than the standard daily-hours setting is not auto-OT merely because
    of its scheduled length. Only approved work outside the exact scheduled
    window is payable as OT.
    """
    employee_id = int(employee["id"])
    standard_paid_hours = float(get_setting(conn, "standard_daily_paid_hours", "8") or 8)
    hourly_rate = float(employee.get("hourly_rate") or 0)

    schedules = trusted_schedule_rows(conn, period_start, period_end, employee_id)
    by_id = {
        int(row["scheduled_shift_id"]): row
        for row in schedules
        if row.get("scheduled_shift_id")
    }
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in schedules:
        by_date.setdefault(str(row["work_date"]), []).append(row)

    logs = fetchall(
        conn,
        """
        SELECT * FROM time_logs
        WHERE employee_id=? AND work_date BETWEEN ? AND ?
          AND attendance_status != 'Rejected'
          AND COALESCE(is_absent,0)=0
        ORDER BY work_date, actual_in, id
        """,
        (employee_id, period_start, period_end),
    )

    matched_by_date: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for log in logs:
        schedule = _matched_schedule(log, by_id, by_date)
        if not schedule:
            continue
        work_date = str(log["work_date"])
        matched_by_date.setdefault(work_date, []).append((log, schedule))

    changed_dates: set[str] = set()
    regular_hours_delta = 0.0
    regular_pay_delta = 0.0
    ot_hours_delta = 0.0
    ot_pay_delta = 0.0
    holiday_pay_delta = 0.0

    for work_date, pairs in matched_by_date.items():
        distinct_shift_ids = {
            int(schedule.get("scheduled_shift_id") or 0)
            for _, schedule in pairs
            if int(schedule.get("scheduled_shift_id") or 0) > 0
        }
        if len(distinct_shift_ids) < 2:
            continue

        old_regular_allocated = 0.0
        for log, schedule in pairs:
            break_minutes = int(
                schedule.get("break_minutes")
                if schedule.get("break_minutes") is not None
                else employee.get("unpaid_break_minutes") or 0
            )
            comp = compute_overlap(
                str(schedule["shift_start"]),
                str(schedule["shift_end"]),
                work_date,
                log.get("actual_in"),
                log.get("actual_out"),
                break_minutes,
            )
            paid_actual = round(float(comp.get("paid_actual_hours") or 0), 4)
            inside = round(float(comp.get("worked_inside_schedule_hours") or 0), 4)
            outside = round(max(0.0, paid_actual - inside), 4)
            approved_outside = round(
                min(float(log.get("approved_ot_hours") or 0), outside),
                4,
            )

            # Reconstruct the legacy day-level allocation so we can remove
            # exactly the regular/OT classification it previously produced.
            old_remaining = max(0.0, standard_paid_hours - old_regular_allocated)
            old_regular = round(min(old_remaining, inside), 4)
            old_inside_ot = round(max(0.0, inside - old_regular), 4)
            old_regular_allocated = round(old_regular_allocated + old_regular, 4)
            old_ot = round(old_inside_ot + approved_outside, 4)

            # Hidden Oasis split-shift policy: every paid hour that falls inside
            # this separately scheduled shift is regular. OT is only approved
            # work outside this shift's scheduled window.
            new_regular = inside
            new_ot = approved_outside

            if abs(new_regular - old_regular) < 0.0001 and abs(new_ot - old_ot) < 0.0001:
                continue

            changed_dates.add(work_date)
            base_multiplier, _ = day_pay_multipliers(
                conn,
                work_date,
                bool(schedule.get("is_rest_day")),
            )
            regular_delta = new_regular - old_regular
            ot_delta = new_ot - old_ot
            regular_hours_delta += regular_delta
            regular_pay_delta += regular_delta * hourly_rate
            ot_hours_delta += ot_delta
            ot_pay_delta += ot_delta * hourly_rate * overtime_multiplier(conn, base_multiplier)
            if base_multiplier > 1.0:
                holiday_pay_delta += regular_delta * hourly_rate * (base_multiplier - 1.0)

    if not changed_dates:
        return result

    result.regular_hours = round(float(result.regular_hours or 0) + regular_hours_delta, 4)
    result.regular_pay = money(float(result.regular_pay or 0) + regular_pay_delta)
    result.approved_ot_hours = round(float(result.approved_ot_hours or 0) + ot_hours_delta, 4)
    result.ot_pay = money(float(result.ot_pay or 0) + ot_pay_delta)
    result.holiday_pay = money(float(result.holiday_pay or 0) + holiday_pay_delta)

    # Any legacy "inside-schedule beyond 8" warning on an independent
    # split-shift date is now invalid because scheduled time is regular by rule.
    filtered_warnings: list[str] = []
    for warning in list(result.warnings or []):
        if warning.startswith("Inside-schedule hours beyond ") and any(
            day in warning for day in changed_dates
        ):
            continue
        filtered_warnings.append(warning)
    result.warnings = filtered_warnings

    # Gross pay and statutory deductions depend on the regular/OT split, so
    # refresh those amounts after applying the per-shift policy.
    from core.payroll_fractional_leave import _recompute_statutory_and_net

    _recompute_statutory_and_net(conn, result, employee, period_start)
    return result


def compute_payroll_per_shift(conn: Any, period_start: str, period_end: str) -> list[Any]:
    from core.payroll_engine import compute_payroll

    results = compute_payroll(conn, period_start, period_end)
    adjusted: list[Any] = []
    for result in results:
        employee = fetchone(conn, "SELECT * FROM employees WHERE id=?", (int(result.employee_id),))
        if employee and str(employee.get("employment_type") or "").lower() != "freelance":
            result = apply_independent_split_shift_allocation(
                conn,
                result,
                employee,
                period_start,
                period_end,
            )
        adjusted.append(result)
    return adjusted
