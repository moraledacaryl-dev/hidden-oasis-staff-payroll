from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from core.db import fetchall, fetchone, get_setting
from core.money import money
from core.payroll_engine import combine_dt, compute_overlap, interval_overlap, overtime_multiplier, shift_window
from core.schedule_source import trusted_schedule_rows

REGULAR = "Regular Holiday"
SPECIAL = "Special Non-Working Day"


@dataclass
class PaySegment:
    start: datetime
    end: datetime
    paid_hours: float
    kind: str  # regular | ot

    @property
    def work_date(self) -> str:
        return self.start.date().isoformat()


def canonical_holiday_type(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"regular", "regular holiday"}:
        return REGULAR
    if text in {"special", "special holiday", "special non-working day", "special non working day"}:
        return SPECIAL
    return None


def active_holiday(conn: Any, work_date: str) -> dict[str, Any] | None:
    row = fetchone(
        conn,
        "SELECT * FROM holidays WHERE holiday_date=? AND active=1",
        (work_date,),
    )
    if not row:
        return None
    kind = canonical_holiday_type(row.get("holiday_type"))
    if not kind:
        return None
    result = dict(row)
    result["holiday_type"] = kind
    return result


def is_rest_day(conn: Any, employee_id: int, work_date: str) -> bool:
    table = fetchone(
        conn,
        "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name='schedule_day_markers'",
    )
    if not table or not int(table.get("c") or 0):
        return False
    row = fetchone(
        conn,
        """
        SELECT id FROM schedule_day_markers
        WHERE employee_id=? AND work_date=? AND marker_type='Rest Day' AND active=1
        LIMIT 1
        """,
        (employee_id, work_date),
    )
    return bool(row)


def day_multiplier(conn: Any, employee_id: int, work_date: str) -> tuple[float, str, str | None]:
    holiday = active_holiday(conn, work_date)
    rest = is_rest_day(conn, employee_id, work_date)
    if holiday and holiday["holiday_type"] == REGULAR and rest:
        return float(get_setting(conn, "regular_holiday_rest_day_multiplier", "2.60") or 2.60), f"Regular Holiday + Rest Day: {holiday['name']}", REGULAR
    if holiday and holiday["holiday_type"] == SPECIAL and rest:
        return float(get_setting(conn, "special_holiday_rest_day_multiplier", "1.50") or 1.50), f"Special Non-Working Day + Rest Day: {holiday['name']}", SPECIAL
    if holiday and holiday["holiday_type"] == REGULAR:
        return float(get_setting(conn, "regular_holiday_multiplier", "2.00") or 2.00), f"Regular Holiday: {holiday['name']}", REGULAR
    if holiday and holiday["holiday_type"] == SPECIAL:
        return float(get_setting(conn, "special_holiday_multiplier", "1.30") or 1.30), f"Special Non-Working Day: {holiday['name']}", SPECIAL
    if rest:
        return float(get_setting(conn, "rest_day_multiplier", "1.30") or 1.30), "Rest Day", None
    return 1.0, "Ordinary Day", None


def _table_exists(conn: Any, table: str) -> bool:
    row = fetchone(
        conn,
        "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return bool(row and int(row.get("c") or 0))


def _paid_leave_on(conn: Any, employee_id: int, work_date: str) -> bool:
    if not _table_exists(conn, "leave_requests") or not _table_exists(conn, "leave_types"):
        return False
    row = fetchone(
        conn,
        """
        SELECT lr.id
        FROM leave_requests lr
        JOIN leave_types lt ON lt.id=lr.leave_type_id
        WHERE lr.employee_id=?
          AND lr.status='Approved'
          AND COALESCE(lt.paid,0)=1
          AND date(lr.start_date) <= date(?)
          AND date(lr.end_date) >= date(?)
        LIMIT 1
        """,
        (employee_id, work_date, work_date),
    )
    return bool(row)


def regular_holiday_eligibility(conn: Any, employee_id: int, holiday_date: str) -> tuple[bool | None, str]:
    """Evaluate the DOLE preceding-workday condition when local records can prove it.

    True/False means the immediately preceding recorded workday is determinable.
    None means the app lacks enough schedule history; callers preserve pay rather than
    silently underpay and surface a warning for payroll review.
    """
    holiday = date.fromisoformat(holiday_date)
    for offset in range(1, 32):
        candidate = (holiday - timedelta(days=offset)).isoformat()
        if is_rest_day(conn, employee_id, candidate):
            continue

        schedules = []
        if _table_exists(conn, "scheduled_shifts"):
            schedules = fetchall(
                conn,
                "SELECT id FROM scheduled_shifts WHERE employee_id=? AND date(shift_date)=date(?)",
                (employee_id, candidate),
            )
        worked = fetchone(
            conn,
            """
            SELECT id FROM time_logs
            WHERE employee_id=? AND date(work_date)=date(?)
              AND COALESCE(attendance_status,'') != 'Rejected'
              AND COALESCE(is_absent,0)=0
              AND actual_in IS NOT NULL AND actual_out IS NOT NULL
            LIMIT 1
            """,
            (employee_id, candidate),
        ) if _table_exists(conn, "time_logs") else None
        paid_leave = _paid_leave_on(conn, employee_id, candidate)

        if schedules:
            if worked:
                return True, f"worked preceding workday {candidate}"
            if paid_leave:
                return True, f"approved paid leave on preceding workday {candidate}"
            return False, f"did not work and had no approved paid leave on preceding workday {candidate}"

        absent = fetchone(
            conn,
            """
            SELECT id FROM time_logs
            WHERE employee_id=? AND date(work_date)=date(?)
              AND COALESCE(attendance_status,'') != 'Rejected'
              AND COALESCE(is_absent,0)=1
            LIMIT 1
            """,
            (employee_id, candidate),
        ) if _table_exists(conn, "time_logs") else None
        if worked or paid_leave:
            return True, f"recorded work/paid leave on preceding workday {candidate}"
        if absent:
            return False, f"recorded unpaid absence on preceding workday {candidate}"
    return None, "preceding workday could not be proven from 31 days of schedule/attendance history"


def _split_interval(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    result: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min)
        boundary = min(end, midnight)
        result.append((cursor, boundary))
        cursor = boundary
    return result


def _raw_hours(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600.0)


def _paid_segments(start: datetime, end: datetime, paid_hours: float, kind: str) -> list[PaySegment]:
    pieces = _split_interval(start, end)
    raw_total = sum(_raw_hours(a, b) for a, b in pieces)
    if raw_total <= 0 or paid_hours <= 0:
        return []
    paid_total = min(raw_total, max(0.0, paid_hours))
    # Break timing is not stored. Allocate unpaid break proportionally across
    # calendar segments so midnight classification is deterministic and neutral.
    result: list[PaySegment] = []
    remaining = paid_total
    for index, (a, b) in enumerate(pieces):
        raw = _raw_hours(a, b)
        if index == len(pieces) - 1:
            paid = remaining
        else:
            paid = min(remaining, paid_total * (raw / raw_total))
        paid = round(max(0.0, paid), 6)
        if paid > 0:
            result.append(PaySegment(a, b, paid, kind))
        remaining = max(0.0, remaining - paid)
    return result


def _take_hours(segments: list[PaySegment], hours: float, kind: str) -> tuple[list[PaySegment], list[PaySegment]]:
    taken: list[PaySegment] = []
    leftover: list[PaySegment] = []
    remaining = max(0.0, hours)
    for seg in segments:
        if remaining <= 0:
            leftover.append(seg)
            continue
        take = min(seg.paid_hours, remaining)
        raw = _raw_hours(seg.start, seg.end)
        ratio = take / seg.paid_hours if seg.paid_hours > 0 else 0.0
        cut = seg.start + (seg.end - seg.start) * min(1.0, ratio)
        if take > 0:
            taken.append(PaySegment(seg.start, cut, take, kind))
        rem = seg.paid_hours - take
        if rem > 0:
            leftover.append(PaySegment(cut, seg.end, rem, seg.kind))
        remaining -= take
    return taken, leftover


def _night_raw_hours(start: datetime, end: datetime) -> float:
    total = 0.0
    cursor = start.date() - timedelta(days=1)
    while cursor <= end.date():
        nd_start = datetime.combine(cursor, time(22, 0))
        nd_end = datetime.combine(cursor + timedelta(days=1), time(6, 0))
        total += interval_overlap(start, end, nd_start, nd_end)
        cursor += timedelta(days=1)
    return total


def _night_paid_hours(segment: PaySegment) -> float:
    raw = _raw_hours(segment.start, segment.end)
    if raw <= 0:
        return 0.0
    return min(segment.paid_hours, _night_raw_hours(segment.start, segment.end) * (segment.paid_hours / raw))


def _log_segments(
    conn: Any,
    emp: dict[str, Any],
    log: dict[str, Any],
    sched: dict[str, Any] | None,
    daily_regular_allocated: dict[str, float],
) -> list[PaySegment]:
    if not log.get("actual_in") or not log.get("actual_out") or log.get("is_absent"):
        return []
    work_date = str(log["work_date"])
    if sched:
        break_mins = int(sched.get("break_minutes") if sched.get("break_minutes") is not None else emp.get("unpaid_break_minutes") or 0)
        s_start, s_end = shift_window(work_date, str(sched["shift_start"]), str(sched["shift_end"]))
    else:
        break_mins = int(emp.get("unpaid_break_minutes") or 0)
        s_start, s_end = shift_window(work_date, str(log.get("actual_in") or "00:00"), str(log.get("actual_out") or "00:00"))
    a_start = combine_dt(work_date, str(log.get("actual_in")))
    a_end = combine_dt(work_date, str(log.get("actual_out")))
    if not a_start or not a_end:
        return []
    if a_end <= a_start:
        a_end += timedelta(days=1)

    comp = compute_overlap(
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
    standard_paid_hours = float(get_setting(conn, "standard_daily_paid_hours", "8") or 8)
    allocated = daily_regular_allocated.get(work_date, 0.0)
    regular_hours = min(max(0.0, standard_paid_hours - allocated), inside_paid)
    daily_regular_allocated[work_date] = round(allocated + regular_hours, 4)
    inside_ot = max(0.0, inside_paid - regular_hours)
    approved_outside = min(float(log.get("approved_ot_hours") or 0), outside_paid)

    inside_start = max(a_start, s_start)
    inside_end = min(a_end, s_end)
    inside_segments = _paid_segments(inside_start, inside_end, inside_paid, "inside") if inside_end > inside_start else []
    regular, remaining_inside = _take_hours(inside_segments, regular_hours, "regular")
    auto_ot, _ = _take_hours(remaining_inside, inside_ot, "ot")

    outside_raw: list[PaySegment] = []
    if a_start < s_start:
        outside_raw.extend(_paid_segments(a_start, min(a_end, s_start), _raw_hours(a_start, min(a_end, s_start)), "outside"))
    if a_end > s_end:
        outside_raw.extend(_paid_segments(max(a_start, s_end), a_end, _raw_hours(max(a_start, s_end), a_end), "outside"))
    outside_ot, _ = _take_hours(outside_raw, approved_outside, "ot")
    return regular + auto_ot + outside_ot


def apply_holiday_payroll_adjustment(
    conn: Any,
    result: Any,
    emp: dict[str, Any],
    period_start: str,
    period_end: str,
) -> bool:
    """Recalculate holiday/rest/OT/ND pay from calendar-segmented attendance.

    Returns True when a monetary/hour field changed. Existing saved payroll
    snapshots are untouched because this only operates while computing a new
    preview, draft, or controlled revision.
    """
    employee_id = int(emp["id"])
    hourly_rate = float(emp.get("hourly_rate") or 0)
    if str(emp.get("employment_type") or "").lower() == "freelance":
        return False
    nd_rate = float(get_setting(conn, "night_diff_rate", "0.10") or 0.10)
    standard_paid_hours = float(get_setting(conn, "standard_daily_paid_hours", "8") or 8)

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
    by_id = {int(s["scheduled_shift_id"]): s for s in schedules if s.get("scheduled_shift_id")}
    by_date: dict[str, list[dict[str, Any]]] = {}
    for schedule in schedules:
        by_date.setdefault(str(schedule["work_date"]), []).append(schedule)

    daily_regular_allocated: dict[str, float] = {}
    segments: list[PaySegment] = []
    worked_dates: set[str] = set()
    paid_leave_dates: set[str] = set()
    for log in logs:
        work_date = str(log["work_date"])
        if log.get("is_absent"):
            worked_dates.add(work_date)
            continue
        shift_id = int(log.get("scheduled_shift_id") or 0)
        sched = by_id.get(shift_id) if shift_id else None
        if not sched and not shift_id:
            candidates = by_date.get(work_date, [])
            if len(candidates) == 1:
                sched = candidates[0]
        log_segs = _log_segments(conn, emp, log, sched, daily_regular_allocated)
        segments.extend(log_segs)
        if log_segs:
            worked_dates.update(seg.work_date for seg in log_segs)

    if _table_exists(conn, "leave_requests") and _table_exists(conn, "leave_types"):
        leaves = fetchall(
            conn,
            """
            SELECT lr.start_date,lr.end_date
            FROM leave_requests lr JOIN leave_types lt ON lt.id=lr.leave_type_id
            WHERE lr.employee_id=? AND lr.status='Approved' AND COALESCE(lt.paid,0)=1
              AND date(lr.start_date) <= date(?) AND date(lr.end_date) >= date(?)
            """,
            (employee_id, period_end, period_start),
        )
        ps, pe = date.fromisoformat(period_start), date.fromisoformat(period_end)
        for leave in leaves:
            cur = max(ps, date.fromisoformat(str(leave["start_date"])[:10]))
            end = min(pe, date.fromisoformat(str(leave["end_date"])[:10]))
            while cur <= end:
                paid_leave_dates.add(cur.isoformat())
                cur += timedelta(days=1)

    new_ot_pay = 0.0
    new_nd_pay = 0.0
    new_nd_hours = 0.0
    special_rest_premium = 0.0
    regular_hours_by_date: dict[str, float] = {}
    regular_multiplier_by_date: dict[str, float] = {}

    for seg in segments:
        multiplier, label, holiday_type = day_multiplier(conn, employee_id, seg.work_date)
        nd_hours = _night_paid_hours(seg)
        new_nd_hours += nd_hours
        if seg.kind == "ot":
            ot_mult = overtime_multiplier(conn, multiplier)
            new_ot_pay += seg.paid_hours * hourly_rate * ot_mult
            new_nd_pay += nd_hours * hourly_rate * nd_rate * ot_mult
        else:
            new_nd_pay += nd_hours * hourly_rate * nd_rate * multiplier
            if holiday_type == REGULAR:
                regular_hours_by_date[seg.work_date] = regular_hours_by_date.get(seg.work_date, 0.0) + seg.paid_hours
                regular_multiplier_by_date[seg.work_date] = max(regular_multiplier_by_date.get(seg.work_date, 1.0), multiplier)
            elif multiplier > 1.0:
                special_rest_premium += seg.paid_hours * hourly_rate * (multiplier - 1.0)

    holiday_pay = special_rest_premium
    active_regular = fetchall(
        conn,
        "SELECT * FROM holidays WHERE active=1 AND holiday_date BETWEEN ? AND ? ORDER BY holiday_date",
        (period_start, period_end),
    )
    for holiday in active_regular:
        if canonical_holiday_type(holiday.get("holiday_type")) != REGULAR:
            continue
        holiday_date = str(holiday["holiday_date"])
        worked_regular = regular_hours_by_date.get(holiday_date, 0.0)
        eligibility, reason = regular_holiday_eligibility(conn, employee_id, holiday_date)
        if worked_regular > 0:
            multiplier = regular_multiplier_by_date.get(holiday_date, 2.0)
            if eligibility is False:
                holiday_pay += worked_regular * hourly_rate * (multiplier - 1.0)
                if result.warnings is not None:
                    result.warnings.append(f"Regular holiday eligibility on {holiday_date}: {reason}; worked hours still receive the worked-holiday rate.")
            else:
                holiday_pay += standard_paid_hours * hourly_rate
                holiday_pay += worked_regular * hourly_rate * max(0.0, multiplier - 2.0)
                if eligibility is None and result.warnings is not None:
                    result.warnings.append(f"Regular holiday eligibility on {holiday_date} needs review: {reason}; base holiday pay was preserved to avoid silent underpayment.")
        elif holiday_date not in paid_leave_dates:
            if eligibility is not False:
                holiday_pay += standard_paid_hours * hourly_rate
                if eligibility is None and result.warnings is not None:
                    result.warnings.append(f"Regular holiday eligibility on {holiday_date} needs review: {reason}; base holiday pay was preserved to avoid silent underpayment.")
            elif result.warnings is not None:
                result.warnings.append(f"No unworked regular-holiday base pay on {holiday_date}: {reason}.")

    old = (
        round(float(result.holiday_pay or 0), 2),
        round(float(result.ot_pay or 0), 2),
        round(float(result.night_diff_pay or 0), 2),
        round(float(result.night_diff_hours or 0), 4),
    )
    result.holiday_pay = money(holiday_pay)
    result.ot_pay = money(new_ot_pay)
    result.night_diff_pay = money(new_nd_pay)
    result.night_diff_hours = round(new_nd_hours, 4)
    new = (
        result.holiday_pay,
        result.ot_pay,
        result.night_diff_pay,
        result.night_diff_hours,
    )
    return old != new
