from __future__ import annotations

from typing import Any


def install() -> None:
    """Patch the legacy payroll engine so distinct scheduled shifts get distinct regular buckets.

    The legacy engine allocates regular hours by calendar date. Hidden Oasis treats
    two separately scheduled shifts on the same date as separate shifts, so each
    scheduled_shift_id must receive its own regular-hours allowance. This wrapper
    corrects the legacy result at the engine boundary until the allocation block is
    moved directly into the consolidated payroll engine.
    """
    from . import payroll_engine as engine

    if getattr(engine.compute_employee_payroll, "_independent_shift_patch", False):
        return

    original = engine.compute_employee_payroll

    def compute_employee_payroll(
        conn: Any,
        emp: dict[str, Any],
        period_start: str,
        period_end: str,
    ):
        result = original(conn, emp, period_start, period_end)
        if str(emp.get("employment_type", "")).lower() == "freelance":
            return result

        schedules = engine.trusted_schedule_rows(
            conn,
            period_start,
            period_end,
            int(emp["id"]),
        )
        schedules_by_id = {
            int(row["scheduled_shift_id"]): row
            for row in schedules
            if row.get("scheduled_shift_id")
        }
        schedules_by_date: dict[str, set[int]] = {}
        for row in schedules:
            shift_id = int(row.get("scheduled_shift_id") or 0)
            if shift_id:
                schedules_by_date.setdefault(str(row["work_date"]), set()).add(shift_id)

        split_dates = {
            work_date
            for work_date, shift_ids in schedules_by_date.items()
            if len(shift_ids) > 1
        }
        if not split_dates:
            return result

        logs = engine.fetchall(
            conn,
            """
            SELECT * FROM time_logs
            WHERE employee_id=? AND work_date BETWEEN ? AND ?
              AND attendance_status != 'Rejected'
            ORDER BY work_date, actual_in, id
            """,
            (emp["id"], period_start, period_end),
        )

        standard_paid_hours = float(
            engine.get_setting(conn, "standard_daily_paid_hours", "8") or 8
        )
        hourly_rate = float(emp.get("hourly_rate") or 0)
        old_day_allocated: dict[str, float] = {}
        new_shift_allocated: dict[tuple[str, int], float] = {}
        changed_dates: set[str] = set()
        dates_with_true_shift_ot: set[str] = set()

        for log in logs:
            work_date = str(log.get("work_date") or "")
            if work_date not in split_dates or log.get("is_absent"):
                continue

            shift_id = int(log.get("scheduled_shift_id") or 0)
            schedule = schedules_by_id.get(shift_id)
            if not schedule:
                # Never guess attendance ownership when multiple shifts exist.
                continue

            break_mins = int(
                schedule.get("break_minutes")
                if schedule.get("break_minutes") is not None
                else emp.get("unpaid_break_minutes") or 0
            )
            comp = engine.compute_overlap(
                schedule["shift_start"],
                schedule["shift_end"],
                work_date,
                log.get("actual_in"),
                log.get("actual_out"),
                break_mins,
            )
            inside_paid = round(
                float(comp.get("worked_inside_schedule_hours") or 0), 4
            )

            old_allocated = old_day_allocated.get(work_date, 0.0)
            old_regular = round(
                min(max(0.0, standard_paid_hours - old_allocated), inside_paid),
                4,
            )
            old_auto_ot = round(max(0.0, inside_paid - old_regular), 4)
            old_day_allocated[work_date] = round(old_allocated + old_regular, 4)

            shift_key = (work_date, shift_id)
            new_allocated = new_shift_allocated.get(shift_key, 0.0)
            new_regular = round(
                min(max(0.0, standard_paid_hours - new_allocated), inside_paid),
                4,
            )
            new_auto_ot = round(max(0.0, inside_paid - new_regular), 4)
            new_shift_allocated[shift_key] = round(new_allocated + new_regular, 4)

            if new_auto_ot > 0.0001:
                dates_with_true_shift_ot.add(work_date)

            regular_delta = round(new_regular - old_regular, 4)
            auto_ot_delta = round(new_auto_ot - old_auto_ot, 4)
            if abs(regular_delta) <= 0.0001 and abs(auto_ot_delta) <= 0.0001:
                continue

            changed_dates.add(work_date)
            base_multiplier, day_label = engine.day_pay_multipliers(
                conn,
                work_date,
                bool(schedule.get("is_rest_day")),
            )

            result.regular_hours += regular_delta
            result.regular_pay += regular_delta * hourly_rate
            result.approved_ot_hours += auto_ot_delta
            result.ot_pay += (
                auto_ot_delta
                * hourly_rate
                * engine.overtime_multiplier(conn, base_multiplier)
            )

            # Special-holiday/rest-day premiums are based on regular hours.
            # Regular-holiday guarantees are day-level and are corrected by the
            # existing holiday payroll adjustment layer, so do not duplicate them.
            if base_multiplier > 1.0 and "Regular Holiday" not in day_label:
                result.holiday_pay += (
                    regular_delta * hourly_rate * (base_multiplier - 1.0)
                )

        if not changed_dates:
            return result

        result.regular_hours = round(max(0.0, result.regular_hours), 4)
        result.approved_ot_hours = round(max(0.0, result.approved_ot_hours), 4)
        result.regular_pay = engine.money(result.regular_pay)
        result.ot_pay = engine.money(max(0.0, result.ot_pay))
        result.holiday_pay = engine.money(result.holiday_pay)

        # Remove the legacy warning only where the apparent OT was caused solely
        # by sharing one calendar-day bucket across distinct scheduled shifts.
        filtered: list[str] = []
        for warning in result.warnings or []:
            remove = False
            for work_date in changed_dates - dates_with_true_shift_ot:
                if (
                    f"Inside-schedule hours beyond {standard_paid_hours:g} on {work_date} "
                    "were paid as OT."
                ) == warning:
                    remove = True
                    break
            if not remove:
                filtered.append(warning)
        result.warnings = filtered

        # The legacy engine already calculated statutory deductions from the old
        # gross. Recompute them once from the corrected regular/OT classification.
        from .payroll_fractional_leave import _recompute_statutory_and_net

        _recompute_statutory_and_net(conn, result, emp, period_start)
        return result

    compute_employee_payroll._independent_shift_patch = True  # type: ignore[attr-defined]
    engine.compute_employee_payroll = compute_employee_payroll
