from __future__ import annotations

from typing import Any


def install() -> None:
    """Align holiday/rest-day monetary segmentation with canonical OT allocation.

    The holiday adjustment rebuilds OT and holiday/rest-day money from attendance
    segments. Night differential is rebuilt separately by ``night_diff_policy``
    from payable regular/approved-OT intervals, so the holiday pass must not
    overwrite that canonical ND result afterward.
    """
    from . import holiday_payroll as holiday

    if not getattr(holiday._log_segments, "_canonical_shift_ot_policy", False):

        def _log_segments(
            conn: Any,
            emp: dict[str, Any],
            log: dict[str, Any],
            sched: dict[str, Any] | None,
            regular_allocated: dict[str, float],
        ) -> list[Any]:
            if not log.get("actual_in") or not log.get("actual_out") or log.get("is_absent"):
                return []

            work_date = str(log["work_date"])
            if sched:
                break_mins = int(
                    sched.get("break_minutes")
                    if sched.get("break_minutes") is not None
                    else emp.get("unpaid_break_minutes") or 0
                )
                s_start, s_end = holiday.shift_window(
                    work_date,
                    str(sched["shift_start"]),
                    str(sched["shift_end"]),
                )
                shift_id = int(sched.get("scheduled_shift_id") or 0)
                allocation_key = (
                    f"shift:{shift_id}"
                    if shift_id
                    else f"shift:{work_date}:{sched.get('shift_start')}:{sched.get('shift_end')}"
                )
            else:
                break_mins = int(emp.get("unpaid_break_minutes") or 0)
                s_start, s_end = holiday.shift_window(
                    work_date,
                    str(log.get("actual_in") or "00:00"),
                    str(log.get("actual_out") or "00:00"),
                )
                allocation_key = f"unscheduled:{work_date}"

            a_start = holiday.combine_dt(work_date, str(log.get("actual_in")))
            a_end = holiday.combine_dt(work_date, str(log.get("actual_out")))
            if not a_start or not a_end:
                return []
            if a_end <= a_start:
                from datetime import timedelta

                a_end += timedelta(days=1)

            comp = holiday.compute_overlap(
                str(sched["shift_start"]) if sched else str(log.get("actual_in") or "00:00"),
                str(sched["shift_end"]) if sched else str(log.get("actual_out") or "00:00"),
                work_date,
                str(log.get("actual_in")),
                str(log.get("actual_out")),
                break_mins,
            )
            inside_paid = float(comp.get("worked_inside_schedule_hours") or 0)
            paid_actual = float(comp.get("paid_actual_hours") or 0)
            outside_paid = max(0.0, paid_actual - inside_paid)
            standard_paid_hours = float(
                holiday.get_setting(conn, "standard_daily_paid_hours", "8") or 8
            )

            allocated = regular_allocated.get(allocation_key, 0.0)
            regular_hours = min(
                max(0.0, standard_paid_hours - allocated),
                inside_paid,
            )
            regular_allocated[allocation_key] = round(allocated + regular_hours, 4)

            if sched:
                inside_ot = max(0.0, inside_paid - regular_hours)
                approved_outside = min(
                    max(0.0, float(log.get("approved_ot_hours") or 0)),
                    outside_paid,
                )
            else:
                # Attendance without a real schedule does not manufacture OT. Only an
                # explicit approval can convert the hours beyond the regular cap to OT.
                excess = max(0.0, inside_paid - regular_hours)
                inside_ot = min(
                    max(0.0, float(log.get("approved_ot_hours") or 0)),
                    excess,
                )
                approved_outside = 0.0

            inside_start = max(a_start, s_start)
            inside_end = min(a_end, s_end)
            inside_segments = (
                holiday._paid_segments(inside_start, inside_end, inside_paid, "inside")
                if inside_end > inside_start
                else []
            )
            regular, remaining_inside = holiday._take_hours(
                inside_segments,
                regular_hours,
                "regular",
            )
            auto_ot, _ = holiday._take_hours(remaining_inside, inside_ot, "ot")

            outside_raw: list[Any] = []
            if a_start < s_start:
                outside_raw.extend(
                    holiday._paid_segments(
                        a_start,
                        min(a_end, s_start),
                        holiday._raw_hours(a_start, min(a_end, s_start)),
                        "outside",
                    )
                )
            if a_end > s_end:
                outside_raw.extend(
                    holiday._paid_segments(
                        max(a_start, s_end),
                        a_end,
                        holiday._raw_hours(max(a_start, s_end), a_end),
                        "outside",
                    )
                )
            outside_ot, _ = holiday._take_hours(
                outside_raw,
                approved_outside,
                "ot",
            )
            return regular + auto_ot + outside_ot

        _log_segments._canonical_shift_ot_policy = True  # type: ignore[attr-defined]
        holiday._log_segments = _log_segments

    if not getattr(
        holiday.apply_holiday_payroll_adjustment,
        "_preserves_canonical_night_diff",
        False,
    ):
        base_apply_holiday_adjustment = holiday.apply_holiday_payroll_adjustment

        def apply_holiday_payroll_adjustment(
            conn: Any,
            result: Any,
            emp: dict[str, Any],
            period_start: str,
            period_end: str,
        ) -> bool:
            # ``night_diff_policy`` already rebuilt these fields from payable
            # regular/approved-OT intervals. The holiday pass still calculates
            # holiday/rest/OT amounts, but its legacy ND reconstruction must not
            # restore ND from a broader attendance interval in the preview path.
            canonical_nd_hours = result.night_diff_hours
            canonical_nd_pay = result.night_diff_pay
            changed = base_apply_holiday_adjustment(
                conn,
                result,
                emp,
                period_start,
                period_end,
            )
            holiday_nd_changed = (
                result.night_diff_hours != canonical_nd_hours
                or result.night_diff_pay != canonical_nd_pay
            )
            result.night_diff_hours = canonical_nd_hours
            result.night_diff_pay = canonical_nd_pay
            return changed or holiday_nd_changed

        apply_holiday_payroll_adjustment._preserves_canonical_night_diff = True  # type: ignore[attr-defined]
        holiday.apply_holiday_payroll_adjustment = apply_holiday_payroll_adjustment
