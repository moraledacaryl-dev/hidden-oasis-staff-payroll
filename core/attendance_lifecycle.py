from __future__ import annotations

from typing import Any, Callable

from core.db import fetchall


def payroll_visible_time_logs(
    conn: Any,
    employee_id: int,
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    """Return attendance rows eligible to drive worked-pay calculations.

    An active Rest Day marker is an explicit employee-day lifecycle decision.
    Attendance that survived from an older import/manual edit on that day is stale
    and must not be payable. This read-side guard complements the write-side purge
    in the Rest Day endpoint and protects historical data until it is repaired.
    """
    return fetchall(
        conn,
        """
        SELECT tl.*
        FROM time_logs tl
        WHERE tl.employee_id=?
          AND tl.work_date BETWEEN ? AND ?
          AND COALESCE(tl.attendance_status, '') != 'Rejected'
          AND NOT EXISTS (
              SELECT 1
              FROM schedule_day_markers marker
              WHERE marker.employee_id=tl.employee_id
                AND date(marker.work_date)=date(tl.work_date)
                AND marker.marker_type='Rest Day'
                AND marker.active=1
          )
        ORDER BY tl.work_date, tl.actual_in, tl.id
        """,
        (employee_id, period_start, period_end),
    )


def _payroll_fetchall_wrapper(original: Callable[..., list[dict[str, Any]]]):
    def guarded(conn: Any, sql: str, params: Any = ()) -> list[dict[str, Any]]:
        normalized = " ".join(str(sql).split()).lower()
        values = tuple(params or ())
        if (
            "select * from time_logs" in normalized
            and "employee_id=?" in normalized
            and "work_date between ? and ?" in normalized
            and len(values) == 3
        ):
            return payroll_visible_time_logs(
                conn,
                int(values[0]),
                str(values[1]),
                str(values[2]),
            )
        return original(conn, sql, params)

    guarded._rest_day_attendance_guard = True  # type: ignore[attr-defined]
    return guarded


def install() -> None:
    """Guard all payroll attendance readers against stale Rest Day rows.

    The payroll stack currently has three compatibility layers that each read
    time_logs directly. Bind their local fetchall imports to the same lifecycle
    filter until schema/payroll decomposition removes these shims.
    """
    from core import holiday_payroll, payroll_engine, payroll_split_shift_policy

    for module in (payroll_engine, payroll_split_shift_policy, holiday_payroll):
        current = module.fetchall
        if getattr(current, "_rest_day_attendance_guard", False):
            continue
        module.fetchall = _payroll_fetchall_wrapper(current)
