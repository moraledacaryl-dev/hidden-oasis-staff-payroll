from __future__ import annotations

from typing import Any

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
