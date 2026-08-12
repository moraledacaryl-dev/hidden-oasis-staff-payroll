from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, date, time, timedelta
from typing import Any
import sqlite3

from .db import fetchall, fetchone, get_setting, now_iso
from .corrections import eligible_corrections, mark_eligible_corrections_applied
from .quality import build_payroll_preflight_checks, summarize_checks
from .money import money
from .schedule_source import trusted_schedule_rows

TIME_FMT = "%H:%M"
DATE_FMT = "%Y-%m-%d"
REVIEW_STATUS = "For Owner Review"
PAYROLL_HISTORY_STATUSES = (REVIEW_STATUS, "Approved", "Paid", "Locked")


@dataclass
class PayrollResult:
    employee_id: int
    employee_code: str
    full_name: str
    regular_hours: float = 0.0
    regular_pay: float = 0.0
    approved_ot_hours: float = 0.0
    ot_pay: float = 0.0
    night_diff_hours: float = 0.0
    night_diff_pay: float = 0.0
    holiday_pay: float = 0.0
    paid_leave_days: float = 0.0
    paid_leave_pay: float = 0.0
    freelance_pay: float = 0.0
    other_earnings: float = 0.0
    gross_pay: float = 0.0
    late_minutes: float = 0.0
    undertime_minutes: float = 0.0
    unpaid_absence_days: float = 0.0
    sss_ee: float = 0.0
    philhealth_ee: float = 0.0
    pagibig_ee: float = 0.0
    sss_er: float = 0.0
    sss_ec: float = 0.0
    philhealth_er: float = 0.0
    pagibig_er: float = 0.0
    tax: float = 0.0
    cash_advance_deduction: float = 0.0
    other_deductions: float = 0.0
    total_deductions: float = 0.0
    net_pay: float = 0.0
    warnings: list[str] | None = None

    def as_db_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["warnings"] = " | ".join(self.warnings or [])
        return data


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), DATE_FMT).date()


def parse_time(value: str | None) -> time | None:
    if value in (None, "", "None"):
        return None
    return datetime.strptime(str(value)[:5], TIME_FMT).time()


def combine_dt(d: str | date, t: str | time | None) -> datetime | None:
    if t in (None, "", "None"):
        return None
    dd = parse_date(d)
    tt = t if isinstance(t, time) else parse_time(str(t))
    return datetime.combine(dd, tt)


def shift_window(work_date: str | date, start: str, end: str) -> tuple[datetime, datetime]:
    s = combine_dt(work_date, start)
    e = combine_dt(work_date, end)
    if e <= s:
        e += timedelta(days=1)
    return s, e


def minutes_between(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a).total_seconds() / 60.0)


def interval_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0.0, (end - start).total_seconds() / 3600.0)


def compute_overlap(
    sched_start: str,
    sched_end: str,
    work_date: str,
    actual_in: str | None,
    actual_out: str | None,
    break_mins: int,
) -> dict[str, float]:
    """Compare scheduled vs actual and subtract unpaid break from paid hours."""
    s_start, s_end = shift_window(work_date, sched_start, sched_end)
    a_start = combine_dt(work_date, actual_in)
    a_end = combine_dt(work_date, actual_out)
    if not a_start or not a_end:
        return {
            "scheduled_hours": round(minutes_between(s_start, s_end) / 60, 4),
            "actual_hours": 0.0,
            "paid_actual_hours": 0.0,
            "worked_inside_schedule_hours": 0.0,
            "late_minutes": 0.0 if a_start else minutes_between(s_start, s_end),
            "undertime_minutes": 0.0,
            "overstay_hours": 0.0,
        }
    if a_end <= a_start:
        a_end += timedelta(days=1)

    scheduled_hours = minutes_between(s_start, s_end) / 60.0
    actual_hours = minutes_between(a_start, a_end) / 60.0
    paid_actual = max(0.0, actual_hours - (break_mins / 60.0))
    inside_sched = interval_overlap(a_start, a_end, s_start, s_end)
    inside_sched_paid = max(0.0, inside_sched - min(break_mins / 60.0, inside_sched))
    late = max(0.0, minutes_between(s_start, a_start)) if a_start > s_start else 0.0
    undertime = max(0.0, minutes_between(a_end, s_end)) if a_end < s_end else 0.0
    overstay = max(0.0, minutes_between(s_end, a_end) / 60.0) if a_end > s_end else 0.0
    return {
        "scheduled_hours": round(scheduled_hours, 4),
        "actual_hours": round(actual_hours, 4),
        "paid_actual_hours": round(paid_actual, 4),
        "worked_inside_schedule_hours": round(inside_sched_paid, 4),
        "late_minutes": round(late, 2),
        "undertime_minutes": round(undertime, 2),
        "overstay_hours": round(overstay, 4),
    }


def compute_nd_hours(work_date: str, actual_in: str | None, actual_out: str | None, break_mins: int = 0) -> float:
    """Computes night-differential hours between 22:00 and 06:00."""
    a_start = combine_dt(work_date, actual_in)
    a_end = combine_dt(work_date, actual_out)
    if not a_start or not a_end:
        return 0.0
    if a_end <= a_start:
        a_end += timedelta(days=1)

    total = 0.0
    cur_date = a_start.date() - timedelta(days=1)
    while cur_date <= a_end.date():
        nd_start = datetime.combine(cur_date, time(22, 0))
        nd_end = datetime.combine(cur_date + timedelta(days=1), time(6, 0))
        total += interval_overlap(a_start, a_end, nd_start, nd_end)
        cur_date += timedelta(days=1)
    if total > 0 and break_mins > 0:
        # Conservative V2 rule: subtract unpaid break from ND only when ND exists.
        total = max(0.0, total - break_mins / 60.0)
    return round(total, 4)


def get_sss_share(conn: sqlite3.Connection, monthly_salary: float) -> tuple[float, float, float]:
    if monthly_salary <= 0:
        return 0.0, 0.0, 0.0
    row = fetchone(
        conn,
        """
        SELECT ee_share, er_share, ec_share FROM sss_contribution_table
        WHERE active=1 AND ? BETWEEN min_comp AND max_comp
        ORDER BY min_comp LIMIT 1
        """,
        (monthly_salary,),
    )
    if not row:
        return 0.0, 0.0, 0.0
    return float(row["ee_share"]), float(row["er_share"]), float(row.get("ec_share") or 0)


def compute_semi_monthly_withholding_tax(taxable_compensation: float) -> float:
    """Compute PH compensation withholding using the BIR semi-monthly table.

    Table is for compensation paid January 1, 2023 onward. The app only calls
    this when an employee is marked withholding-tax eligible.
    """
    taxable = max(0.0, float(taxable_compensation or 0))
    brackets = [
        (333333.0, 91770.70, 0.35),
        (83333.0, 16770.70, 0.30),
        (33333.0, 4270.70, 0.25),
        (16667.0, 937.50, 0.20),
        (10417.0, 0.0, 0.15),
    ]
    for floor, base_tax, rate in brackets:
        if taxable > floor:
            return money(base_tax + ((taxable - floor) * rate))
    return 0.0


def month_bounds(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    if d.month == 12:
        end = d.replace(year=d.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = d.replace(month=d.month + 1, day=1) - timedelta(days=1)
    return start, end


def get_month_previous_contribs(conn: sqlite3.Connection, employee_id: int, period_start: str) -> dict[str, float]:
    ps = parse_date(period_start)
    mstart, _ = month_bounds(ps)
    rows = fetchall(
        conn,
        """
        SELECT pi.gross_pay, pi.sss_ee, pi.philhealth_ee, pi.pagibig_ee, COALESCE(pi.sss_er,0) AS sss_er, COALESCE(pi.sss_ec,0) AS sss_ec, COALESCE(pi.philhealth_er,0) AS philhealth_er, COALESCE(pi.pagibig_er,0) AS pagibig_er
        FROM payroll_items pi
        JOIN payroll_runs pr ON pr.id = pi.payroll_run_id
        WHERE pi.employee_id=?
          AND pr.period_start >= ?
          AND pr.period_end < ?
          AND pr.status IN ('For Owner Review','Reviewed','Approved','Paid','Locked')
        """,
        (employee_id, mstart.isoformat(), period_start),
    )
    return {
        "gross": sum(float(r["gross_pay"] or 0) for r in rows),
        "sss": sum(float(r["sss_ee"] or 0) for r in rows),
        "philhealth": sum(float(r["philhealth_ee"] or 0) for r in rows),
        "pagibig": sum(float(r["pagibig_ee"] or 0) for r in rows),
        "sss_er": sum(float(r["sss_er"] or 0) for r in rows),
        "sss_ec": sum(float(r["sss_ec"] or 0) for r in rows),
        "philhealth_er": sum(float(r["philhealth_er"] or 0) for r in rows),
        "pagibig_er": sum(float(r["pagibig_er"] or 0) for r in rows),
    }


def day_pay_multipliers(conn: sqlite3.Connection, work_date: str, is_rest_day: bool) -> tuple[float, str]:
    holiday = fetchone(conn, "SELECT * FROM holidays WHERE holiday_date=? AND active=1", (work_date,))
    htype = str(holiday.get("holiday_type") if holiday else "").lower()
    if holiday and "regular" in htype and is_rest_day:
        return float(get_setting(conn, "regular_holiday_rest_day_multiplier", "2.60") or 2.60), f"Regular Holiday + Rest Day: {holiday['name']}"
    if holiday and "special" in htype and is_rest_day:
        return float(get_setting(conn, "special_holiday_rest_day_multiplier", "1.50") or 1.50), f"Special Holiday + Rest Day: {holiday['name']}"
    if holiday and "regular" in htype:
        return float(get_setting(conn, "regular_holiday_multiplier", "2.00") or 2.00), f"Regular Holiday: {holiday['name']}"
    if holiday and "special" in htype:
        return float(get_setting(conn, "special_holiday_multiplier", "1.30") or 1.30), f"Special Holiday: {holiday['name']}"
    if is_rest_day:
        return float(get_setting(conn, "rest_day_multiplier", "1.30") or 1.30), "Rest Day"
    return 1.0, "Ordinary Day"


def overtime_multiplier(conn: sqlite3.Connection, base_day_multiplier: float) -> float:
    if abs(base_day_multiplier - 1.0) < 0.001:
        return float(get_setting(conn, "ot_rate", "1.25") or 1.25)
    return base_day_multiplier * float(get_setting(conn, "premium_day_ot_rate", "1.30") or 1.30)


def compute_employee_payroll(conn: sqlite3.Connection, emp: dict[str, Any], period_start: str, period_end: str) -> PayrollResult:
    warnings: list[str] = []
    hourly_rate = float(emp.get("hourly_rate") or 0)
    standard_paid_hours = float(get_setting(conn, "standard_daily_paid_hours", "8") or 8)
    nd_rate = float(get_setting(conn, "night_diff_rate", "0.10") or 0.10)
    is_freelance = str(emp.get("employment_type", "")).lower() == "freelance"

    result = PayrollResult(
        employee_id=int(emp["id"]),
        employee_code=str(emp["employee_code"]),
        full_name=str(emp["full_name"]),
        warnings=warnings,
    )

    if not is_freelance:
        logs = fetchall(
            conn,
            """
            SELECT * FROM time_logs
            WHERE employee_id=? AND work_date BETWEEN ? AND ?
              AND attendance_status != 'Rejected'
            ORDER BY work_date, actual_in
            """,
            (emp["id"], period_start, period_end),
        )
        scheds = trusted_schedule_rows(
            conn,
            period_start,
            period_end,
            int(emp["id"]),
        )
        sched_by_id = {
            int(schedule["scheduled_shift_id"]): schedule
            for schedule in scheds
            if schedule.get("scheduled_shift_id")
        }
        scheds_by_date: dict[str, list[dict[str, Any]]] = {}
        for schedule in scheds:
            scheds_by_date.setdefault(
                str(schedule["work_date"]),
                [],
            ).append(schedule)

        daily_regular_allocated: dict[str, float] = {}
        holiday_rows = fetchall(
            conn,
            "SELECT * FROM holidays WHERE active=1 AND holiday_date BETWEEN ? AND ?",
            (period_start, period_end),
        )
        regular_holidays = {
            str(h["holiday_date"]): h
            for h in holiday_rows
            if "regular" in str(h.get("holiday_type") or "").lower()
        }
        regular_holiday_base_paid_dates: set[str] = set()
        log_dates = set()

        for log in logs:
            if not log.get("actual_in") and not log.get("is_absent"):
                warnings.append(f"Missing time-in on {log['work_date']}; no hours paid unless corrected.")
            if not log.get("actual_out") and not log.get("is_absent"):
                warnings.append(f"Missing time-out on {log['work_date']}; no hours paid unless corrected.")
            if log.get("is_absent"):
                work_date = str(log["work_date"])
                if work_date in regular_holidays:
                    result.holiday_pay += standard_paid_hours * hourly_rate
                    regular_holiday_base_paid_dates.add(work_date)
                    warnings.append(f"Regular holiday base pay on {work_date} was paid even though employee was absent.")
                else:
                    result.unpaid_absence_days += 1
                log_dates.add(work_date)
                continue
            work_date = str(log["work_date"])
            scheduled_shift_id = int(
                log.get("scheduled_shift_id") or 0
            )

            sched = (
                sched_by_id.get(scheduled_shift_id)
                if scheduled_shift_id
                else None
            )

            if not sched and not scheduled_shift_id:
                candidates = scheds_by_date.get(work_date, [])
                if len(candidates) == 1:
                    sched = candidates[0]
                elif len(candidates) > 1:
                    warnings.append(
                        f"Attendance on {work_date} is not linked to a "
                        "specific shift; multiple shifts exist, so payroll "
                        "uses actual time without assigning it to both shifts."
                    )

            if sched:
                break_mins = int(
                    sched.get("break_minutes")
                    if sched.get("break_minutes") is not None
                    else emp.get("unpaid_break_minutes") or 0
                )
                s_start = sched["shift_start"]
                s_end = sched["shift_end"]
                is_rest_day = bool(sched.get("is_rest_day"))
            else:
                warnings.append(
                    f"No unambiguous schedule found for {work_date}; "
                    "paid based on this actual log only."
                )
                break_mins = int(emp.get("unpaid_break_minutes") or 0)
                s_start = log.get("actual_in") or "00:00"
                s_end = log.get("actual_out") or "00:00"
                is_rest_day = False

            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
            paid_actual = comp["paid_actual_hours"]

            # Hidden Oasis payroll rule:
            # 1) Paid hours are limited to actual work inside the scheduled window.
            # 2) Inside-schedule paid hours beyond the standard paid day (default 8) are OT.
            # 3) Outside-schedule early/late time is paid only when approved as OT.
            inside_schedule_paid = round(float(comp.get("worked_inside_schedule_hours") or 0), 4)
            outside_schedule_paid = round(max(0.0, paid_actual - inside_schedule_paid), 4)
            approved_ot = float(log.get("approved_ot_hours") or 0)

            regular_already_allocated = daily_regular_allocated.get(
                work_date,
                0.0,
            )
            remaining_regular_for_day = max(
                0.0,
                standard_paid_hours - regular_already_allocated,
            )
            regular_hours = round(
                min(remaining_regular_for_day, inside_schedule_paid),
                4,
            )
            auto_inside_schedule_ot = round(
                max(0.0, inside_schedule_paid - regular_hours),
                4,
            )
            daily_regular_allocated[work_date] = round(
                regular_already_allocated + regular_hours,
                4,
            )
            approved_outside_schedule_ot = round(min(approved_ot, outside_schedule_paid), 4)
            detected_extra = round(auto_inside_schedule_ot + outside_schedule_paid, 4)
            payable_ot = round(auto_inside_schedule_ot + approved_outside_schedule_ot, 4)

            # Safety guard: regular + paid OT must never exceed actual paid worked hours.
            if regular_hours + payable_ot > paid_actual + 0.0001:
                payable_ot = round(max(0.0, paid_actual - regular_hours), 4)

            if auto_inside_schedule_ot > 0:
                warnings.append(f"Inside-schedule hours beyond {standard_paid_hours:g} on {log['work_date']} were paid as OT.")
            if outside_schedule_paid > 0 and approved_ot <= 0:
                warnings.append(f"Unapproved outside-schedule time on {log['work_date']} was detected but not paid as OT.")
            elif approved_ot > outside_schedule_paid + 0.01:
                warnings.append(f"Approved OT on {log['work_date']} exceeds outside-schedule worked time; payroll uses worked outside-schedule OT only.")
            if log.get("attendance_status") in ("Pending", "Needs Manager", "Disputed"):
                warnings.append(f"Attendance on {log['work_date']} is still {log.get('attendance_status')}.")
            if log.get("ot_status") == "Pending":
                warnings.append(f"OT on {log['work_date']} is still pending General Manager approval.")

            base_multiplier, day_label = day_pay_multipliers(conn, log["work_date"], is_rest_day)
            base_regular_pay = regular_hours * hourly_rate
            result.regular_hours += regular_hours
            result.regular_pay += base_regular_pay
            if base_multiplier > 1.0:
                if "Regular Holiday" in day_label:
                    # The regular-holiday guarantee is a day-level amount.
                    # Multiple shifts on the same date must not duplicate it.
                    holiday_date = str(log["work_date"])
                    if holiday_date not in regular_holiday_base_paid_dates:
                        holiday_pay_for_day = money(
                            max(
                                standard_paid_hours * hourly_rate,
                                base_regular_pay * (base_multiplier - 1.0),
                            )
                        )
                        result.holiday_pay += holiday_pay_for_day
                        regular_holiday_base_paid_dates.add(holiday_date)
                        warnings.append(
                            f"{holiday_date} uses {day_label}; holiday pay "
                            f"is guaranteed once for the day at a minimum of "
                            f"{standard_paid_hours:g} hours."
                        )
                else:
                    # Special holiday/rest-day premiums remain based on actual paid regular hours.
                    result.holiday_pay += money(
                        base_regular_pay * (base_multiplier - 1.0)
                    )
                    warnings.append(f"{log['work_date']} uses {day_label} multiplier {base_multiplier:.2f}x.")

            result.approved_ot_hours += payable_ot
            result.ot_pay += payable_ot * hourly_rate * overtime_multiplier(conn, base_multiplier)
            result.late_minutes += comp["late_minutes"]
            result.undertime_minutes += comp["undertime_minutes"]
            raw_nd = compute_nd_hours(log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins=break_mins)
            payable_hours_for_nd = round(regular_hours + payable_ot, 4)
            nd = round(min(raw_nd, payable_hours_for_nd), 4)
            result.night_diff_hours += nd
            result.night_diff_pay += nd * hourly_rate * nd_rate * base_multiplier
            log_dates.add(log["work_date"])

        # Scheduled days without logs and without approved leave become unpaid absence warnings.
        approved_leave_dates = set()
        paid_leave_dates = set()
        leave_rows = fetchall(
            conn,
            """
            SELECT lr.*, lt.paid, lt.name AS leave_name
            FROM leave_requests lr
            JOIN leave_types lt ON lt.id=lr.leave_type_id
            WHERE lr.employee_id=? AND lr.status='Approved'
              AND lr.start_date <= ? AND lr.end_date >= ?
            """,
            (emp["id"], period_end, period_start),
        )
        for lr in leave_rows:
            ent = fetchone(
                conn,
                """
                SELECT * FROM employee_leave_entitlements
                WHERE employee_id=? AND leave_type_id=? AND year=?
                """,
                (emp["id"], lr["leave_type_id"], parse_date(lr["start_date"]).year),
            )
            leave_start = parse_date(lr["start_date"])
            leave_end = parse_date(lr["end_date"])
            period_s = parse_date(period_start)
            period_e = parse_date(period_end)
            overlap_start = max(leave_start, period_s)
            overlap_end = min(leave_end, period_e)
            overlap_dates = []
            d = overlap_start
            while d <= overlap_end:
                d_iso = d.isoformat()
                approved_leave_dates.add(d_iso)
                if d_iso not in paid_leave_dates:
                    overlap_dates.append(d_iso)
                d += timedelta(days=1)
            paid_days_in_cutoff = float(len(overlap_dates))
            if int(lr.get("paid") or 0) and paid_days_in_cutoff > 0:
                if not ent or not int(ent.get("entitled") or 0):
                    warnings.append(f"Approved paid leave '{lr['leave_name']}' exists but employee entitlement is not enabled.")
                elif float(ent.get("used") or 0) > float(ent.get("credits") or 0) + 0.001:
                    warnings.append(f"Leave '{lr['leave_name']}' usage exceeds configured credits.")
                else:
                    for d_iso in overlap_dates:
                        paid_leave_dates.add(d_iso)
                    result.paid_leave_days += paid_days_in_cutoff
                    result.paid_leave_pay += paid_days_in_cutoff * standard_paid_hours * hourly_rate
                    warnings.append(f"Paid leave '{lr['leave_name']}' pays {paid_days_in_cutoff:g} unique day(s) x {standard_paid_hours:g} standard hours.")

        for hol_date in regular_holidays:
            if hol_date in regular_holiday_base_paid_dates or hol_date in log_dates or hol_date in approved_leave_dates:
                continue
            result.holiday_pay += standard_paid_hours * hourly_rate
            regular_holiday_base_paid_dates.add(hol_date)
            warnings.append(f"Regular holiday base pay on {hol_date} was paid even with no worked log.")

        for work_date, day_schedules in scheds_by_date.items():
            if work_date in regular_holidays:
                continue
            if day_schedules and all(
                bool(schedule.get("is_rest_day"))
                for schedule in day_schedules
            ):
                continue
            if work_date not in log_dates and work_date not in approved_leave_dates:
                result.unpaid_absence_days += 1
                warnings.append(
                    f"Scheduled day {work_date} has no time log or "
                    "approved leave; counted as one unpaid absence day."
                )

        result.regular_pay = money(result.regular_pay)
        result.ot_pay = money(result.ot_pay)
        result.night_diff_pay = money(result.night_diff_pay)
        result.holiday_pay = money(result.holiday_pay)

    # Output-based workers: manual weekly approved outputs within period.
    outputs = fetchall(
        conn,
        """
        SELECT fo.*, frt.name AS output_name
        FROM freelance_outputs fo
        JOIN freelance_rate_types frt ON frt.id=fo.output_type_id
        WHERE fo.employee_id=? AND fo.status='Approved'
          AND fo.week_start <= ? AND fo.week_end >= ?
        """,
        (emp["id"], period_end, period_start),
    )
    result.freelance_pay = money(
        sum(
            float(o["approved_qty"] or 0) * float(o["rate"] or 0)
            for o in outputs
        )
    )

    # Manual approved adjustments for the payroll period.
    adjustments = fetchall(
        conn,
        """
        SELECT * FROM payroll_adjustments
        WHERE employee_id=? AND status='Approved'
          AND period_start <= ? AND period_end >= ?
        """,
        (emp["id"], period_end, period_start),
    )
    for adj in adjustments:
        amount = float(adj.get("amount") or 0)
        if str(adj.get("kind", "")).lower() == "deduction":
            result.other_deductions += amount
        else:
            result.other_earnings += amount

    for correction in eligible_corrections(conn, int(emp["id"]), period_start):
        amount = abs(float(correction.get("amount") or 0))
        if amount <= 0:
            continue
        if correction.get("adjustment_type") == "Deduction":
            result.other_deductions += amount
        else:
            result.other_earnings += amount
        warnings.append(
            f"Correction #{correction['id']} from payroll run {correction['payroll_run_id']} is included in this run."
        )

    result.gross_pay = money(
        result.regular_pay
        + result.ot_pay
        + result.night_diff_pay
        + result.holiday_pay
        + result.paid_leave_pay
        + result.freelance_pay
        + result.other_earnings
    )

    prev = get_month_previous_contribs(conn, int(emp["id"]), period_start)
    declared = float(emp.get("declared_monthly_base") or 0)
    has_current_gross = result.gross_pay > 0.005

    # SSS: preserve Caryl's intended actual month-to-date gross catch-up method.
    # Employer share/EC use the same month-to-date catch-up structure so accounting can accrue the employer liability.
    if has_current_gross and int(emp.get("benefits_sss") or 0):
        month_gross_basis = prev["gross"] + result.gross_pay
        sss_month_ee, sss_month_er, sss_month_ec = get_sss_share(conn, month_gross_basis)
        result.sss_ee = money(max(0.0, sss_month_ee - prev["sss"]))
        result.sss_er = money(max(0.0, sss_month_er - prev["sss_er"]))
        result.sss_ec = money(max(0.0, sss_month_ec - prev["sss_ec"]))

    # PhilHealth: declared monthly basis, split/catch up across cutoffs.
    if has_current_gross and int(emp.get("benefits_philhealth") or 0):
        ph_rate = float(get_setting(conn, "philhealth_rate", "0.05") or 0.05)
        ph_floor = float(get_setting(conn, "philhealth_floor", "10000") or 10000)
        ph_ceiling = float(get_setting(conn, "philhealth_ceiling", "100000") or 100000)
        ph_base = min(max(declared or ph_floor, ph_floor), ph_ceiling)
        ph_month_ee = (ph_base * ph_rate) / 2.0
        ph_month_er = ph_month_ee
        if parse_date(period_start).day <= 15:
            result.philhealth_ee = money(ph_month_ee / 2.0)
            result.philhealth_er = money(ph_month_er / 2.0)
        else:
            result.philhealth_ee = money(max(0.0, ph_month_ee - prev["philhealth"]))
            result.philhealth_er = money(max(0.0, ph_month_er - prev["philhealth_er"]))

    # Pag-IBIG: declared monthly basis with configurable ceiling, split/catch up.
    if has_current_gross and int(emp.get("benefits_pagibig") or 0):
        pi_rate = float(get_setting(conn, "pagibig_rate", "0.02") or 0.02)
        pi_er_rate = float(get_setting(conn, "pagibig_employer_rate", "0.02") or 0.02)
        pi_ceiling = float(get_setting(conn, "pagibig_ceiling", "10000") or 10000)
        pi_base = min(declared, pi_ceiling)
        pi_month_ee = pi_base * pi_rate
        pi_month_er = pi_base * pi_er_rate
        if parse_date(period_start).day <= 15:
            result.pagibig_ee = money(pi_month_ee / 2.0)
            result.pagibig_er = money(pi_month_er / 2.0)
        else:
            result.pagibig_ee = money(max(0.0, pi_month_ee - prev["pagibig"]))
            result.pagibig_er = money(max(0.0, pi_month_er - prev["pagibig_er"]))

    if has_current_gross and int(emp.get("benefits_tax") or 0):
        taxable_comp = result.gross_pay - result.sss_ee - result.philhealth_ee - result.pagibig_ee
        result.tax = compute_semi_monthly_withholding_tax(taxable_comp)

    # Cash advance deduction: default schedule, custom override allowed, capped so net does not go negative.
    statutory_and_manual = result.sss_ee + result.philhealth_ee + result.pagibig_ee + result.tax + result.other_deductions
    ca_capacity = max(0.0, result.gross_pay - statutory_and_manual)
    ca_rows = fetchall(
        conn,
        """
        SELECT * FROM cash_advances
        WHERE employee_id=? AND outstanding_balance > 0
          AND status IN ('Released','Partially Paid','Approved')
        ORDER BY request_date, id
        """,
        (emp["id"],),
    )
    ca_deduction = 0.0
    for ca in ca_rows:
        raw = ca.get("custom_next_deduction")
        scheduled = float(raw) if raw not in (None, "") else float(ca.get("repayment_per_cutoff") or 0)
        if scheduled <= 0 or ca_capacity <= ca_deduction:
            continue
        amount = min(float(ca["outstanding_balance"]), scheduled, ca_capacity - ca_deduction)
        ca_deduction += amount
    result.cash_advance_deduction = money(ca_deduction)

    result.total_deductions = money(
        statutory_and_manual + result.cash_advance_deduction
    )
    result.net_pay = money(
        result.gross_pay - result.total_deductions
    )
    result.regular_hours = round(result.regular_hours, 4)
    result.approved_ot_hours = round(result.approved_ot_hours, 4)
    result.night_diff_hours = round(result.night_diff_hours, 4)
    result.late_minutes = round(result.late_minutes, 2)
    result.undertime_minutes = round(result.undertime_minutes, 2)
    result.paid_leave_pay = money(result.paid_leave_pay)
    result.other_earnings = money(result.other_earnings)
    result.other_deductions = money(result.other_deductions)
    return result


def compute_payroll(conn: sqlite3.Connection, period_start: str, period_end: str) -> list[PayrollResult]:
    employees = fetchall(conn, "SELECT * FROM employees WHERE status NOT IN ('Inactive','Terminated') ORDER BY full_name")
    return [compute_employee_payroll(conn, emp, period_start, period_end) for emp in employees]


def save_payroll_draft(
    conn: sqlite3.Connection,
    period_start: str,
    period_end: str,
    payout_date: str,
    run_label: str,
    prepared_by: str,
    results: list[PayrollResult],
) -> int:
    existing = fetchone(conn, "SELECT * FROM payroll_runs WHERE period_start=? AND period_end=? AND run_label=?", (period_start, period_end, run_label))
    if existing and existing.get("status") in ("Approved", "Paid", "Locked"):
        raise ValueError("Cannot replace an approved/paid/locked payroll run. Reopen it with a reason first.")
    validation_summary = summarize_checks(build_payroll_preflight_checks(conn, period_start, period_end))
    conn.execute(
        """
        INSERT INTO payroll_runs(period_start, period_end, payout_date, run_label, status, prepared_by, validation_summary, created_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(period_start, period_end, run_label)
        DO UPDATE SET payout_date=excluded.payout_date, status='Draft', prepared_by=excluded.prepared_by, validation_summary=excluded.validation_summary, created_at=excluded.created_at
        """,
        (period_start, period_end, payout_date, run_label, "Draft", prepared_by, validation_summary, now_iso()),
    )
    run_id = conn.execute(
        "SELECT id FROM payroll_runs WHERE period_start=? AND period_end=? AND run_label=?",
        (period_start, period_end, run_label),
    ).fetchone()[0]
    conn.execute("DELETE FROM payroll_items WHERE payroll_run_id=?", (run_id,))
    for r in results:
        data = r.as_db_dict()
        cols = [
            "payroll_run_id", "employee_id", "regular_hours", "regular_pay", "approved_ot_hours", "ot_pay",
            "night_diff_hours", "night_diff_pay", "holiday_pay", "paid_leave_days", "paid_leave_pay",
            "freelance_pay", "other_earnings", "gross_pay", "late_minutes", "undertime_minutes",
            "unpaid_absence_days", "sss_ee", "philhealth_ee", "pagibig_ee", "sss_er", "sss_ec", "philhealth_er", "pagibig_er", "tax",
            "cash_advance_deduction", "other_deductions", "total_deductions", "net_pay", "warnings", "created_at"
        ]
        values = [
            run_id, data["employee_id"], data["regular_hours"], data["regular_pay"], data["approved_ot_hours"], data["ot_pay"],
            data["night_diff_hours"], data["night_diff_pay"], data["holiday_pay"], data["paid_leave_days"], data["paid_leave_pay"],
            data["freelance_pay"], data["other_earnings"], data["gross_pay"], data["late_minutes"], data["undertime_minutes"],
            data["unpaid_absence_days"], data["sss_ee"], data["philhealth_ee"], data["pagibig_ee"], data["sss_er"], data["sss_ec"], data["philhealth_er"], data["pagibig_er"], data["tax"],
            data["cash_advance_deduction"], data["other_deductions"], data["total_deductions"], data["net_pay"], data["warnings"], now_iso()
        ]
        placeholders = ",".join(["?"] * len(cols))
        cur2 = conn.execute(f"INSERT INTO payroll_items({','.join(cols)}) VALUES({placeholders})", values)
        add_payroll_lines(conn, cur2.lastrowid, r)
    mark_eligible_corrections_applied(conn, int(run_id), period_start)
    conn.commit()
    return int(run_id)


def add_payroll_lines(conn: sqlite3.Connection, item_id: int, r: PayrollResult) -> None:
    lines = [
        ("earning", "Regular Pay", r.regular_pay, r.regular_hours, None, None, "Actual approved regular hours", 10),
        ("earning", "Holiday/Rest Premium", r.holiday_pay, None, None, None, "Premium above ordinary hourly pay", 15),
        ("earning", "Approved OT Pay", r.ot_pay, r.approved_ot_hours, None, None, "Manager-approved OT only", 20),
        ("earning", "Night Differential", r.night_diff_pay, r.night_diff_hours, None, None, "10 PM to 6 AM", 30),
        ("earning", "Paid Leave", r.paid_leave_pay, None, r.paid_leave_days, None, "Approved paid leave", 40),
        ("earning", "Freelance Output Pay", r.freelance_pay, None, None, None, "Approved manual outputs", 50),
        ("earning", "Other Earnings", r.other_earnings, None, None, None, "Approved payroll adjustments", 60),
        ("deduction", "SSS EE", r.sss_ee, None, None, None, "Actual MTD gross catch-up method", 110),
        ("deduction", "PhilHealth EE", r.philhealth_ee, None, None, None, "Declared monthly basis split/catch-up", 120),
        ("deduction", "Pag-IBIG EE", r.pagibig_ee, None, None, None, "Declared monthly basis split/catch-up", 130),
        ("deduction", "Withholding Tax", r.tax, None, None, None, "BIR semi-monthly compensation withholding table", 135),
        ("employer", "SSS ER", r.sss_er, None, None, None, "Employer SSS share for accounting", 210),
        ("employer", "SSS EC", r.sss_ec, None, None, None, "Employer EC share for accounting", 215),
        ("employer", "PhilHealth ER", r.philhealth_er, None, None, None, "Employer PhilHealth share for accounting", 220),
        ("employer", "Pag-IBIG ER", r.pagibig_er, None, None, None, "Employer Pag-IBIG share for accounting", 230),
        ("deduction", "Cash Advance Repayment", r.cash_advance_deduction, None, None, None, "Linked to outstanding staff cash advance", 140),
        ("deduction", "Other Deductions", r.other_deductions, None, None, None, "Approved payroll adjustments", 150),
    ]
    for kind, label, amount, hours, days, qty, notes, sort_order in lines:
        if abs(float(amount or 0)) < 0.005:
            continue
        conn.execute(
            """
            INSERT INTO payroll_item_lines(payroll_item_id, kind, label, amount, hours, days, quantity, notes, sort_order)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (item_id, kind, label, amount, hours, days, qty, notes, sort_order),
        )


def apply_cash_advance_repayments(conn: sqlite3.Connection, run_id: int) -> None:
    existing = fetchone(conn, "SELECT COUNT(*) AS c FROM cash_advance_repayments WHERE payroll_run_id=?", (run_id,))
    if existing and int(existing["c"] or 0) > 0:
        return
    run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
    if not run:
        return
    items = fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=? AND cash_advance_deduction > 0", (run_id,))
    for item in items:
        remaining = float(item["cash_advance_deduction"] or 0)
        advances = fetchall(
            conn,
            """
            SELECT * FROM cash_advances
            WHERE employee_id=? AND outstanding_balance > 0
              AND status IN ('Released','Partially Paid','Approved')
            ORDER BY request_date, id
            """,
            (item["employee_id"],),
        )
        for ca in advances:
            if remaining <= 0:
                break
            amount = money(
                min(
                    remaining,
                    float(ca["outstanding_balance"] or 0),
                )
            )
            new_balance = money(
                float(ca["outstanding_balance"] or 0) - amount
            )
            new_status = "Fully Paid" if new_balance <= 0.005 else "Partially Paid"
            conn.execute(
                "INSERT INTO cash_advance_repayments(cash_advance_id, payroll_run_id, payment_date, amount, method, notes, created_at) VALUES(?,?,?,?,?,?,?)",
                (ca["id"], run_id, run["payout_date"], amount, "Payroll Deduction", f"Auto-applied from payroll run {run_id}", now_iso()),
            )
            conn.execute("UPDATE cash_advances SET outstanding_balance=?, status=? WHERE id=?", (max(0.0, new_balance), new_status, ca["id"]))
            remaining = money(remaining - amount)


def reverse_cash_advance_repayments(conn: sqlite3.Connection, run_id: int) -> None:
    rows = fetchall(conn, "SELECT * FROM cash_advance_repayments WHERE payroll_run_id=?", (run_id,))
    for r in rows:
        ca = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (r["cash_advance_id"],))
        if ca:
            restored = money(
                float(ca["outstanding_balance"] or 0)
                + float(r["amount"] or 0)
            )
            status = "Released" if restored >= float(ca["amount"] or 0) - 0.005 else "Partially Paid"
            conn.execute("UPDATE cash_advances SET outstanding_balance=?, status=? WHERE id=?", (restored, status, ca["id"]))
    conn.execute("DELETE FROM cash_advance_repayments WHERE payroll_run_id=?", (run_id,))


def create_accounting_queue_for_payroll(conn: sqlite3.Connection, run_id: int) -> None:
    existing = fetchone(conn, "SELECT COUNT(*) AS c FROM accounting_export_queue WHERE source_type='Payroll Run' AND source_id=?", (run_id,))
    if existing and int(existing["c"] or 0) > 0:
        return
    run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
    totals = fetchone(
        conn,
        """
        SELECT COALESCE(SUM(gross_pay),0) AS gross,
               COALESCE(SUM(net_pay),0) AS net,
               COALESCE(SUM(sss_ee),0) AS sss,
               COALESCE(SUM(philhealth_ee),0) AS philhealth,
               COALESCE(SUM(pagibig_ee),0) AS pagibig,
               COALESCE(SUM(tax),0) AS tax,
               COALESCE(SUM(sss_er),0) AS sss_er,
               COALESCE(SUM(sss_ec),0) AS sss_ec,
               COALESCE(SUM(philhealth_er),0) AS philhealth_er,
               COALESCE(SUM(pagibig_er),0) AS pagibig_er,
               COALESCE(SUM(cash_advance_deduction),0) AS ca
        FROM payroll_items WHERE payroll_run_id=?
        """,
        (run_id,),
    )
    if not run or not totals:
        return
    entry_date = run["payout_date"]
    desc = f"Payroll {run['period_start']} to {run['period_end']} ({run['run_label']})"
    cash_account = get_setting(conn, "payroll_cash_account", "Payroll Bank / Cash") or "Payroll Bank / Cash"
    lines = [
        ("Salaries and Wages Expense", "Salaries Payable", totals["gross"], desc + " - gross payroll"),
        ("Salaries Payable", "SSS Payable", totals["sss"], desc + " - employee SSS"),
        ("Salaries Payable", "PhilHealth Payable", totals["philhealth"], desc + " - employee PhilHealth"),
        ("Salaries Payable", "Pag-IBIG Payable", totals["pagibig"], desc + " - employee Pag-IBIG"),
        ("Salaries Payable", "Withholding Tax Payable", totals["tax"], desc + " - employee withholding tax"),
        ("Employer Contributions Expense", "SSS Payable", float(totals["sss_er"] or 0) + float(totals["sss_ec"] or 0), desc + " - employer SSS/EC"),
        ("Employer Contributions Expense", "PhilHealth Payable", totals["philhealth_er"], desc + " - employer PhilHealth"),
        ("Employer Contributions Expense", "Pag-IBIG Payable", totals["pagibig_er"], desc + " - employer Pag-IBIG"),
        ("Salaries Payable", "Employee Cash Advance Receivable", totals["ca"], desc + " - cash advance repayment"),
        ("Salaries Payable", cash_account, totals["net"], desc + " - net pay release"),
    ]
    for debit, credit, amount, line_desc in lines:
        amount = round(float(amount or 0), 2)
        if amount <= 0:
            continue
        conn.execute(
            """
            INSERT INTO accounting_export_queue(source_type, source_id, entry_date, description, debit_account, credit_account, amount, status, created_at)
            VALUES('Payroll Run',?,?,?,?,?,?, 'For Review', ?)
            """,
            (run_id, entry_date, line_desc, debit, credit, amount, now_iso()),
        )


def create_accounting_queue_for_13th_month(conn: sqlite3.Connection, run_id: int) -> None:
    existing = fetchone(conn, "SELECT COUNT(*) AS c FROM accounting_export_queue WHERE source_type='13th Month' AND source_id=?", (run_id,))
    if existing and int(existing["c"] or 0) > 0:
        return
    run = fetchone(conn, "SELECT * FROM payroll_13th_month_runs WHERE id=?", (run_id,))
    emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (run["employee_id"],)) if run else None
    if not run or not emp:
        return
    amount = money(run.get("net_13th_pay"))
    if amount <= 0:
        return
    entry_date = run.get("release_date") or now_iso()[:10]
    desc = f"13th Month Pay {run['year']} - {emp['full_name']}"
    cash_account = get_setting(conn, "payroll_cash_account", "Payroll Bank / Cash") or "Payroll Bank / Cash"
    conn.execute(
        """
        INSERT INTO accounting_export_queue(source_type, source_id, entry_date, description, debit_account, credit_account, amount, status, created_at)
        VALUES('13th Month',?,?,?,?,?,?, 'For Review', ?)
        """,
        (run_id, entry_date, desc, "13th Month Pay Expense", cash_account, amount, now_iso()),
    )
    conn.commit()


def normalize_payroll_status(status: str | None) -> str:
    value = str(status or "").strip()
    return REVIEW_STATUS if value == "Reviewed" else value


def update_payroll_status(conn: sqlite3.Connection, run_id: int, status: str, actor: str, reason: str | None = None) -> None:
    now = now_iso()
    run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
    if not run:
        raise ValueError(f"Payroll run {run_id} not found")
    old_status_raw = str(run["status"])
    old_status = normalize_payroll_status(old_status_raw)
    status = normalize_payroll_status(status)
    allowed = {
        "Draft": {REVIEW_STATUS},
        REVIEW_STATUS: {"Approved", "Draft"},
        "Approved": {"Paid", "Locked", "Draft"},
        "Paid": {"Locked", "Draft"},
        "Locked": {"Draft"},
    }
    if status != old_status and status not in allowed.get(old_status, set()):
        raise ValueError(f"Invalid payroll status transition: {old_status} to {status}.")
    if status == "Draft" and old_status != "Draft" and not reason:
        raise ValueError("A reopen reason is required before returning payroll to Draft.")
    if status in ("Approved", "Paid"):
        checks = build_payroll_preflight_checks(conn, run["period_start"], run["period_end"])
        blockers = [c for c in checks if c.get("severity") == "Blocker"]
        if blockers:
            raise ValueError(f"Payroll QA has {len(blockers)} blocker(s). Resolve them before {status.lower()}.")
    if status == "Paid":
        apply_cash_advance_repayments(conn, run_id)
        conn.execute("UPDATE payroll_runs SET status=?, paid_at=? WHERE id=?", (status, now, run_id))
        create_accounting_queue_for_payroll(conn, run_id)
        try:
            from core.integration_accounting import enqueue_payroll_run
            enqueue_payroll_run(conn, run_id)
        except Exception as exc:
            conn.execute(
                "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
                (actor, "Payroll integration event creation failed", "payroll_runs", run_id, str(exc), now),
            )
    elif status == "Approved":
        conn.execute("UPDATE payroll_runs SET status=?, approved_by=?, approved_at=? WHERE id=?", (status, actor, now, run_id))
        try:
            from core.integration_accounting import enqueue_payroll_run
            enqueue_payroll_run(conn, run_id)
        except Exception as exc:
            conn.execute(
                "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
                (actor, "Payroll approved integration event creation failed", "payroll_runs", run_id, str(exc), now),
            )
    elif status == "Locked":
        conn.execute("UPDATE payroll_runs SET status=?, locked_at=? WHERE id=?", (status, now, run_id))
    elif status == REVIEW_STATUS:
        conn.execute("UPDATE payroll_runs SET status=?, locked_at=?, prepared_by=COALESCE(prepared_by, ?) WHERE id=?", (status, now, actor, run_id))
    elif status == "Draft" and reason:
        if old_status in ("Paid", "Locked"):
            reverse_cash_advance_repayments(conn, run_id)
            conn.execute("UPDATE accounting_export_queue SET status='Reversed' WHERE source_type='Payroll Run' AND source_id=? AND status='For Review'", (run_id,))
        conn.execute(
            "UPDATE payroll_runs SET status=?, reopen_reason=?, approved_by=NULL, approved_at=NULL, locked_at=NULL WHERE id=?",
            (status, reason, run_id),
        )
    else:
        conn.execute("UPDATE payroll_runs SET status=? WHERE id=?", (status, run_id))
    conn.execute(
        "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
        (actor, f"Payroll status changed from {old_status_raw} to {status}", "payroll_runs", run_id, reason or "", now),
    )
    conn.commit()


def compute_13th_month_basis(conn: sqlite3.Connection, employee_id: int, year: int) -> float:
    """Compute 13th month basis from saved payroll history.

    Policy: regular/basic pay plus paid leave pay only.
    It intentionally excludes OT, night differential, holiday/rest premiums,
    other earnings, allowances, freelance output pay, and reimbursements.
    """
    rows = fetchall(
        conn,
        """
        SELECT pi.regular_pay, pi.paid_leave_pay
        FROM payroll_items pi
        JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
        WHERE pi.employee_id=?
          AND substr(pr.period_start,1,4)=?
          AND pr.status IN ('For Owner Review','Reviewed','Approved','Paid','Locked')
        """,
        (employee_id, str(year)),
    )
    return money(
        sum(
            float(r.get("regular_pay") or 0)
            + float(r.get("paid_leave_pay") or 0)
            for r in rows
        )
    )


def save_13th_month_run(
    conn: sqlite3.Connection,
    employee_id: int,
    year: int,
    period_label: str,
    basis_amount: float,
    adjustment_amount: float,
    deductions: float,
    status: str,
    release_date: str | None,
    prepared_by: str,
    notes: str = "",
) -> int:
    base_13th = money(float(basis_amount or 0) / 12.0)
    net = money(
        base_13th
        + float(adjustment_amount or 0)
        - float(deductions or 0)
    )
    now = now_iso()
    conn.execute(
        """
        INSERT INTO payroll_13th_month_runs(
            employee_id, year, period_label, basis_amount, base_13th_amount,
            adjustment_amount, deductions, net_13th_pay, status, release_date,
            prepared_by, notes, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(employee_id, year, period_label) DO UPDATE SET
            basis_amount=excluded.basis_amount,
            base_13th_amount=excluded.base_13th_amount,
            adjustment_amount=excluded.adjustment_amount,
            deductions=excluded.deductions,
            net_13th_pay=excluded.net_13th_pay,
            status=excluded.status,
            release_date=excluded.release_date,
            prepared_by=excluded.prepared_by,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        """,
        (
            employee_id,
            year,
            period_label,
            money(basis_amount),
            base_13th,
            money(adjustment_amount),
            money(deductions),
            net,
            status,
            release_date,
            prepared_by,
            notes,
            now,
            now,
        ),
    )
    run_id = conn.execute(
        "SELECT id FROM payroll_13th_month_runs WHERE employee_id=? AND year=? AND period_label=?",
        (employee_id, year, period_label),
    ).fetchone()[0]
    conn.execute("DELETE FROM payroll_13th_month_lines WHERE run_id=?", (run_id,))
    lines = [
        ("basis", "13th month basis", money(basis_amount), "Regular/basic pay + paid leave pay", 10),
        ("earning", "Base 13th month pay", base_13th, "Basis / 12", 20),
        ("adjustment", "Manual adjustment", money(adjustment_amount), notes, 30),
        ("deduction", "Deductions", money(deductions), notes, 40),
    ]
    for kind, label, amount, line_notes, order in lines:
        if abs(float(amount or 0)) < 0.005 and kind not in ("basis", "earning"):
            continue
        conn.execute(
            "INSERT INTO payroll_13th_month_lines(run_id, kind, label, amount, notes, sort_order) VALUES(?,?,?,?,?,?)",
            (run_id, kind, label, amount, line_notes, order),
        )
    conn.execute(
        "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
        (prepared_by, "Saved 13th month run", "payroll_13th_month_runs", run_id, f"{period_label} / {year}", now),
    )
    if status in ("Approved", "Paid", "Locked"):
        if status in ("Paid", "Locked"):
            create_accounting_queue_for_13th_month(conn, int(run_id))
        try:
            from core.integration_accounting import enqueue_13th_month
            enqueue_13th_month(conn, int(run_id))
        except Exception as exc:
            conn.execute(
                "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
                (prepared_by, "13th month integration event creation failed", "payroll_13th_month_runs", int(run_id), str(exc), now),
            )
    conn.commit()
    return int(run_id)
