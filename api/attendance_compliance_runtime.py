from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, Query

from api.attendance_compliance import (
    classify_late_minutes,
    fetch_compliance_shifts,
    handbook_action,
    is_excused_attendance_row,
    minutes_late_from_times,
    month_bounds,
    require_attendance_compliance_user,
    reward_status,
    router as legacy_router,
    table_exists,
)
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter()

# Preserve existing write handlers unchanged. The compliance GET is redefined
# below so schema creation/ALTER/commit remains a startup responsibility.
for route in legacy_router.routes:
    methods = {str(method).upper() for method in getattr(route, "methods", set())}
    if "GET" not in methods:
        router.routes.append(route)


@router.get("/api/v1/attendance/compliance")
def attendance_compliance_readonly(
    month: str = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_attendance_compliance_user(authorization, x_api_key)
    period_start, period_end = month_bounds(month)
    year_start = date.fromisoformat(period_start).replace(month=1, day=1).isoformat()
    year_end = date.fromisoformat(period_start).replace(month=12, day=31).isoformat()
    conn = get_conn(DB_PATH)
    try:
        employees = fetchall(
            conn,
            """
            SELECT id, employee_code, full_name, department, position
            FROM employees
            WHERE lower(COALESCE(status, 'active')) NOT IN
                  ('inactive', 'terminated', 'resigned', 'separated')
            ORDER BY COALESCE(department, ''), full_name
            """,
        )
        shifts = fetch_compliance_shifts(conn, period_start, period_end)
        actuals = fetchall(
            conn,
            """
            SELECT *
            FROM time_logs
            WHERE date(work_date) BETWEEN date(?) AND date(?)
            """,
            (period_start, period_end),
        ) if table_exists(conn, "time_logs") else []
        year_shifts = fetch_compliance_shifts(conn, year_start, year_end)
        year_actuals = fetchall(
            conn,
            """
            SELECT *
            FROM time_logs
            WHERE date(work_date) BETWEEN date(?) AND date(?)
            """,
            (year_start, year_end),
        ) if table_exists(conn, "time_logs") else []
        memos = fetchall(
            conn,
            """
            SELECT am.*, e.full_name, e.employee_code, e.department
            FROM attendance_memos am
            LEFT JOIN employees e ON e.id=am.employee_id
            WHERE am.period_month=?
            ORDER BY am.issued_at DESC, am.id DESC
            """,
            (month,),
        )

        actual_by_key = {
            (int(row.get("employee_id") or 0), str(row.get("work_date"))[:10]): row
            for row in actuals
            if row.get("employee_id")
        }
        year_actual_by_key = {
            (int(row.get("employee_id") or 0), str(row.get("work_date"))[:10]): row
            for row in year_actuals
            if row.get("employee_id")
        }

        year_counts: dict[int, int] = {}
        for shift in year_shifts:
            employee_id = int(shift.get("employee_id") or 0)
            if not employee_id:
                continue
            work_date = str(shift.get("shift_date"))[:10]
            actual = year_actual_by_key.get((employee_id, work_date))
            if not actual:
                year_counts[employee_id] = year_counts.get(employee_id, 0) + 1
                continue
            if is_excused_attendance_row(actual):
                continue
            absence_type = str(actual.get("absence_type") or "").strip()
            attendance_status = str(actual.get("attendance_status") or "").strip()
            absence_label = absence_type or attendance_status
            absence_label_lower = absence_label.lower()
            if "unexcused" in absence_label_lower or "awol" in absence_label_lower:
                year_counts[employee_id] = year_counts.get(employee_id, 0) + 1
                continue
            minutes = minutes_late_from_times(
                shift.get("start_time"),
                actual.get("actual_in"),
            )
            if minutes is not None and minutes > 5:
                year_counts[employee_id] = year_counts.get(employee_id, 0) + 1

        stats: dict[int, dict[str, Any]] = {}
        for employee in employees:
            employee_id = int(employee["id"])
            stats[employee_id] = {
                "employee_id": employee_id,
                "employee_code": employee.get("employee_code"),
                "full_name": employee.get("full_name"),
                "department": employee.get("department"),
                "position": employee.get("position"),
                "scheduled_shifts": 0,
                "missing_logs": 0,
                "late_infractions": 0,
                "grace_periods": 0,
                "partial_absences": 0,
                "unexcused_absences": 0,
                "awol": 0,
                "approved_absences": 0,
                "year_unexcused_infractions": year_counts.get(employee_id, 0),
                "latest_notice": None,
                "latest_evidence": None,
                "late_details": [],
                "absence_details": [],
            }

        for shift in shifts:
            employee_id = int(shift.get("employee_id") or 0)
            if employee_id not in stats:
                continue
            item = stats[employee_id]
            item["scheduled_shifts"] += 1
            work_date = str(shift.get("shift_date"))[:10]
            actual = actual_by_key.get((employee_id, work_date))
            if not actual:
                item["missing_logs"] += 1
                continue

            absence_type = str(actual.get("absence_type") or "").strip()
            attendance_status = str(actual.get("attendance_status") or "").strip()
            absence_label = absence_type or attendance_status
            absence_label_lower = absence_label.lower()
            looks_like_absence = (
                int(actual.get("is_absent") or 0) == 1
                or "leave" in absence_label_lower
                or "absence" in absence_label_lower
                or "awol" in absence_label_lower
                or "absent" in absence_label_lower
            )

            if looks_like_absence:
                if "unexcused" in absence_label_lower:
                    item["unexcused_absences"] += 1
                elif "awol" in absence_label_lower:
                    item["awol"] += 1
                elif "rest day" not in absence_label_lower and absence_label:
                    item["approved_absences"] += 1
                item["absence_details"].append({
                    "date": work_date,
                    "type": absence_label or "Absent",
                    "notice": actual.get("notice_timing"),
                    "evidence": actual.get("evidence_ref"),
                })
                item["latest_notice"] = actual.get("notice_timing") or item["latest_notice"]
                item["latest_evidence"] = actual.get("evidence_ref") or item["latest_evidence"]
                continue

            minutes = minutes_late_from_times(
                shift.get("start_time"),
                actual.get("actual_in"),
            )
            late_status = classify_late_minutes(minutes)
            if minutes is not None and 1 <= minutes <= 5:
                item["grace_periods"] += 1
            if minutes is not None and minutes > 5:
                item["late_infractions"] += 1
                item["late_details"].append({
                    "date": work_date,
                    "scheduled_start": shift.get("start_time"),
                    "actual_in": actual.get("actual_in"),
                    "minutes_late": minutes,
                    "status": late_status,
                })
            if minutes is not None and minutes > 30:
                item["partial_absences"] += 1

        items: list[dict[str, Any]] = []
        count_fields = [
            "scheduled_shifts",
            "missing_logs",
            "late_infractions",
            "grace_periods",
            "partial_absences",
            "unexcused_absences",
            "awol",
            "approved_absences",
        ]
        for item in stats.values():
            item["handbook_action"] = handbook_action(
                int(item["late_infractions"]),
                int(item["partial_absences"]),
                int(item["unexcused_absences"]),
                int(item["awol"]),
            )
            item["attendance_reward_status"] = reward_status(
                int(item["year_unexcused_infractions"]),
            )
            if any(int(item[key]) for key in count_fields):
                items.append(item)
        items.sort(key=lambda row: (
            row["handbook_action"] == "No action required",
            row.get("department") or "",
            row.get("full_name") or "",
        ))
        return {
            "ok": True,
            "month": month,
            "period_start": period_start,
            "period_end": period_end,
            "checked_by": user.get("display_name"),
            "items": items,
            "memos": memos,
            "mode": "attendance_compliance_scheduled_shifts_only",
        }
    finally:
        conn.close()
