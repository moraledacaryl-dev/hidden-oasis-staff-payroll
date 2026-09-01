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
    """Apply Hidden Oasis regular/OT allocation corrections.

    Rules:
    * Every distinct same-day scheduled shift receives its own regular-hours
      bucket, capped at the configured standard paid hours (normally 8).
    * Paid time inside that scheduled shift beyond its own regular bucket is OT.
    * Approved work outside the scheduled window remains OT.
    * A date with no schedule must not manufacture OT merely because an actual
      attendance log exceeds the daily regular-hours cap. Unscheduled excess
      time is OT only when it has an explicit approved_ot_hours value.
    """
    employee_id = int(employee["id"])
    standard_paid_hours = float(
        get_setting(conn, "standard_daily_paid_hours", "8") or 8
    )
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
    unscheduled_by_date: dict[str, list[dict[str, Any]]] = {}
    for log in logs:
        work_date = str(log["work_date"])
        schedule = _matched_schedule(log, by_id, by_date)
        if schedule:
            matched_by_date.setdefault(work_date, []).append((log, schedule))
        elif not by_date.get(work_date):
            # Narrow fallback correction: only dates that truly have no schedule.
            # Ambiguous/unlinked attendance on a date that does have schedules is
            # intentionally left for attendance remediation rather than guessed.
            unscheduled_by_date.setdefault(work_date, []).append(log)

    changed_dates: set[str] = set()
    split_dates: set[str] = set()
    split_dates_with_inside_ot: set[str] = set()
    unscheduled_dates_with_excess: set[str] = set()
    regular_hours_delta = 0.0
    regular_pay_delta = 0.0
    ot_hours_delta = 0.0
    ot_pay_delta = 0.0
    holiday_pay_delta = 0.0

    # Correct the base engine's shared same-day 8-hour pool into one independent
    # 8-hour pool for every explicitly linked scheduled shift.
    for work_date, pairs in matched_by_date.items():
        distinct_shift_ids = {
            int(schedule.get("scheduled_shift_id") or 0)
            for _, schedule in pairs
            if int(schedule.get("scheduled_shift_id") or 0) > 0
        }
        if len(distinct_shift_ids) < 2:
            continue

        split_dates.add(work_date)
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
            inside = round(
                float(comp.get("worked_inside_schedule_hours") or 0),
                4,
            )
            outside = round(max(0.0, paid_actual - inside), 4)
            approved_outside = round(
                min(float(log.get("approved_ot_hours") or 0), outside),
                4,
            )

            # Reconstruct what the base engine did with its shared day-level pool.
            old_remaining = max(0.0, standard_paid_hours - old_regular_allocated)
            old_regular = round(min(old_remaining, inside), 4)
            old_inside_ot = round(max(0.0, inside - old_regular), 4)
            old_regular_allocated = round(old_regular_allocated + old_regular, 4)
            old_ot = round(old_inside_ot + approved_outside, 4)

            # Correct rule: every shift starts a fresh 8-hour regular bucket;
            # scheduled hours beyond that shift's bucket are OT.
            new_regular = round(min(standard_paid_hours, inside), 4)
            new_inside_ot = round(max(0.0, inside - new_regular), 4)
            new_ot = round(new_inside_ot + approved_outside, 4)
            if new_inside_ot > 0:
                split_dates_with_inside_ot.add(work_date)

            if (
                abs(new_regular - old_regular) < 0.0001
                and abs(new_ot - old_ot) < 0.0001
            ):
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
            ot_pay_delta += (
                ot_delta * hourly_rate * overtime_multiplier(conn, base_multiplier)
            )
            if base_multiplier > 1.0:
                holiday_pay_delta += (
                    regular_delta * hourly_rate * (base_multiplier - 1.0)
                )

    # Correct the base engine's no-schedule fallback. The base path temporarily
    # uses actual-in/out as a synthetic schedule, which otherwise turns every
    # paid hour after the daily cap into automatic OT. With no real schedule,
    # only explicitly approved excess hours may be paid as OT.
    for work_date, day_logs in unscheduled_by_date.items():
        old_regular_allocated = 0.0
        for log in day_logs:
            if not log.get("actual_in") or not log.get("actual_out"):
                continue
            break_minutes = int(employee.get("unpaid_break_minutes") or 0)
            comp = compute_overlap(
                str(log.get("actual_in")),
                str(log.get("actual_out")),
                work_date,
                log.get("actual_in"),
                log.get("actual_out"),
                break_minutes,
            )
            paid_actual = round(float(comp.get("paid_actual_hours") or 0), 4)
            old_remaining = max(0.0, standard_paid_hours - old_regular_allocated)
            old_regular = round(min(old_remaining, paid_actual), 4)
            old_auto_ot = round(max(0.0, paid_actual - old_regular), 4)
            old_regular_allocated = round(old_regular_allocated + old_regular, 4)

            if old_auto_ot <= 0:
                continue

            unscheduled_dates_with_excess.add(work_date)
            approved = max(0.0, float(log.get("approved_ot_hours") or 0))
            new_ot = round(min(approved, old_auto_ot), 4)
            ot_delta = new_ot - old_auto_ot
            if abs(ot_delta) < 0.0001:
                continue

            changed_dates.add(work_date)
            base_multiplier, _ = day_pay_multipliers(conn, work_date, False)
            ot_hours_delta += ot_delta
            ot_pay_delta += (
                ot_delta * hourly_rate * overtime_multiplier(conn, base_multiplier)
            )

    if not changed_dates and not unscheduled_dates_with_excess:
        return result

    result.regular_hours = round(
        float(result.regular_hours or 0) + regular_hours_delta,
        4,
    )
    result.regular_pay = money(float(result.regular_pay or 0) + regular_pay_delta)
    result.approved_ot_hours = round(
        float(result.approved_ot_hours or 0) + ot_hours_delta,
        4,
    )
    result.ot_pay = money(float(result.ot_pay or 0) + ot_pay_delta)
    result.holiday_pay = money(float(result.holiday_pay or 0) + holiday_pay_delta)

    filtered_warnings: list[str] = []
    for warning in list(result.warnings or []):
        if warning.startswith("Inside-schedule hours beyond "):
            matched_split_date = next(
                (day for day in split_dates if day in warning),
                None,
            )
            if (
                matched_split_date
                and matched_split_date not in split_dates_with_inside_ot
            ):
                continue
            if any(day in warning for day in unscheduled_dates_with_excess):
                continue
        if warning.startswith("Approved OT on ") and any(
            day in warning for day in unscheduled_dates_with_excess
        ):
            # The base warning compares approved OT with synthetic
            # outside-schedule time (=0) and is misleading when no schedule exists.
            continue
        filtered_warnings.append(warning)

    for work_date in sorted(unscheduled_dates_with_excess):
        approved_for_day = sum(
            max(0.0, float(log.get("approved_ot_hours") or 0))
            for log in unscheduled_by_date[work_date]
        )
        if approved_for_day <= 0:
            filtered_warnings.append(
                f"Unscheduled hours beyond {standard_paid_hours:g} on {work_date} "
                "were not paid as OT because no OT was explicitly approved."
            )

    result.warnings = filtered_warnings

    from core.payroll_fractional_leave import _recompute_statutory_and_net

    _recompute_statutory_and_net(conn, result, employee, period_start)
    return result


def compute_payroll_per_shift(
    conn: Any,
    period_start: str,
    period_end: str,
) -> list[Any]:
    from core.payroll_engine import compute_payroll

    results = compute_payroll(conn, period_start, period_end)
    adjusted: list[Any] = []
    for result in results:
        employee = fetchone(
            conn,
            "SELECT * FROM employees WHERE id=?",
            (int(result.employee_id),),
        )
        if (
            employee
            and str(employee.get("employment_type") or "").lower() != "freelance"
        ):
            result = apply_independent_split_shift_allocation(
                conn,
                result,
                employee,
                period_start,
                period_end,
            )
        adjusted.append(result)
    return adjusted
