from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.main import ROLE_OWNER, ROLE_PAYROLL, configured_db_path, require_api_key, require_roles
from core.db import fetchall, get_conn

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


def _dates_between(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days: list[str] = []
    while current <= last:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _time_minutes(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = text.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None


def _shift_minutes(start_time: Any, end_time: Any) -> float | None:
    start = _time_minutes(start_time)
    end = _time_minutes(end_time)
    if start is None or end is None:
        return None
    if end <= start:
        end += 24 * 60
    return float(end - start)


def _actual_minutes(actual_in: Any, actual_out: Any) -> float | None:
    start = _time_minutes(actual_in)
    end = _time_minutes(actual_out)
    if start is None or end is None:
        return None
    if end <= start:
        end += 24 * 60
    return float(end - start)


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(rows, key=lambda row: int(row.get("id") or 0), reverse=True)[0]


def _is_biometric(row: dict[str, Any]) -> bool:
    source = str(row.get("source") or "").lower()
    verification = str(row.get("verification_type") or "").lower()
    return "biometric" in source or "biometric" in verification or bool(row.get("device_employee_code"))


def _flag(severity: str, code: str, label: str, action: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "label": label, "recommended_action": action}


@router.get("/payroll/qa")
def payroll_attendance_qa(
    period_start: date = Query(...),
    period_end: date = Query(...),
    include_info: bool = Query(False),
    user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL)),
) -> dict[str, Any]:
    start = period_start.isoformat()
    end = period_end.isoformat()
    if period_end < period_start:
        start, end = end, start

    conn = get_conn(configured_db_path())
    try:
        employees = fetchall(
            conn,
            """
            SELECT id, employee_code, full_name, department, position, status
            FROM employees
            WHERE lower(COALESCE(status, 'active')) NOT IN ('inactive', 'terminated', 'resigned')
            ORDER BY full_name
            """,
        )
        planned = fetchall(
            conn,
            """
            SELECT ss.id, ss.employee_id, ss.shift_date AS work_date, ss.start_time, ss.end_time,
                   ss.position, ss.department, ss.break_minutes, ss.notes, 'planned' AS schedule_source
            FROM scheduled_shifts ss
            WHERE date(ss.shift_date) BETWEEN date(?) AND date(?)
            ORDER BY ss.shift_date, ss.start_time, ss.id
            """,
            (start, end),
        )
        legacy = fetchall(
            conn,
            """
            SELECT s.id, s.employee_id, s.work_date, s.shift_start AS start_time, s.shift_end AS end_time,
                   COALESCE(e.position, '') AS position, COALESCE(s.department, e.department) AS department,
                   s.break_minutes, s.notes, 'legacy' AS schedule_source
            FROM schedules s
            LEFT JOIN employees e ON e.id = s.employee_id
            WHERE date(s.work_date) BETWEEN date(?) AND date(?)
            ORDER BY s.work_date, s.shift_start, s.id
            """,
            (start, end),
        )
        logs = fetchall(
            conn,
            """
            SELECT tl.*, e.full_name AS employee_name, e.employee_code
            FROM time_logs tl
            LEFT JOIN employees e ON e.id = tl.employee_id
            WHERE date(tl.work_date) BETWEEN date(?) AND date(?)
              AND lower(COALESCE(tl.attendance_status, '')) != 'rejected'
            ORDER BY tl.work_date, tl.employee_id, tl.id
            """,
            (start, end),
        )
        leaves = fetchall(
            conn,
            """
            SELECT lr.*, lt.name AS leave_type_name
            FROM leave_requests lr
            LEFT JOIN leave_types lt ON lt.id = lr.leave_type_id
            WHERE lr.start_date <= ? AND lr.end_date >= ?
              AND lower(COALESCE(lr.status, '')) IN ('approved', 'reviewed')
            """,
            (end, start),
        )

        schedules_by_key: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for item in planned + legacy:
            employee_id = int(item.get("employee_id") or 0)
            if employee_id:
                schedules_by_key.setdefault((employee_id, str(item.get("work_date"))[:10]), []).append(item)

        manual_logs_by_key: dict[tuple[int, str], list[dict[str, Any]]] = {}
        biometric_logs_by_key: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for log in logs:
            employee_id = int(log.get("employee_id") or 0)
            work_date = str(log.get("work_date"))[:10]
            if not employee_id or not work_date:
                continue
            if _is_biometric(log):
                biometric_logs_by_key.setdefault((employee_id, work_date), []).append(log)
            else:
                manual_logs_by_key.setdefault((employee_id, work_date), []).append(log)

        leaves_by_key: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for leave in leaves:
            employee_id = int(leave.get("employee_id") or 0)
            if not employee_id:
                continue
            for work_date in _dates_between(max(start, str(leave.get("start_date"))[:10]), min(end, str(leave.get("end_date"))[:10])):
                leaves_by_key.setdefault((employee_id, work_date), []).append(leave)

        rows: list[dict[str, Any]] = []
        totals: dict[str, int] = {"critical": 0, "warning": 0, "info": 0, "rows": 0}

        for employee in employees:
            employee_id = int(employee["id"])
            for work_date in _dates_between(start, end):
                key = (employee_id, work_date)
                schedules = schedules_by_key.get(key, [])
                manual_logs = manual_logs_by_key.get(key, [])
                biometric_logs = biometric_logs_by_key.get(key, [])
                approved_leaves = leaves_by_key.get(key, [])
                actual = _latest(manual_logs)
                biometric = _latest(biometric_logs)
                schedule = schedules[0] if schedules else None
                flags: list[dict[str, str]] = []

                schedule_minutes = _shift_minutes(schedule.get("start_time"), schedule.get("end_time")) if schedule else None
                actual_work_minutes = _actual_minutes(actual.get("actual_in"), actual.get("actual_out")) if actual else None
                schedule_start = _time_minutes(schedule.get("start_time")) if schedule else None
                schedule_end = _time_minutes(schedule.get("end_time")) if schedule else None
                actual_in = _time_minutes(actual.get("actual_in")) if actual else None
                actual_out = _time_minutes(actual.get("actual_out")) if actual else None
                if schedule_start is not None and schedule_end is not None and schedule_end <= schedule_start:
                    schedule_end += 24 * 60
                if actual_in is not None and actual_out is not None and actual_out <= actual_in:
                    actual_out += 24 * 60

                notes = " ".join(str(value or "") for value in [actual.get("attendance_status") if actual else "", actual.get("absence_type") if actual else "", actual.get("notes") if actual else ""]).lower()

                if schedule and not actual and not biometric and not approved_leaves:
                    flags.append(_flag("warning", "SCHEDULED_NO_ATTENDANCE", "Scheduled but no manual actual or biometric punch", "Review as possible absence, missing upload, or schedule error."))
                if actual and not schedule:
                    flags.append(_flag("warning", "ACTUAL_WITHOUT_SCHEDULE", "Actual attendance exists but no schedule", "Confirm if this was unscheduled work or missing schedule."))
                if biometric and not actual:
                    flags.append(_flag("warning", "BIOMETRIC_WITHOUT_MANUAL", "Biometric punch exists but no manual/template actual", "Create actual from biometric or ignore punch with reason."))
                if actual and not biometric and str(actual.get("source") or "").lower() in {"manual", "template_upload", "attendance_template"}:
                    flags.append(_flag("info", "MANUAL_ONLY", "Manual/template actual has no biometric match", "Usually okay if manual log is trusted; review if unusual."))
                if actual and int(actual.get("is_absent") or 0):
                    flags.append(_flag("critical", "MARKED_ABSENT", "Attendance row is marked absent", "Confirm absence type before payroll."))
                if approved_leaves:
                    flags.append(_flag("info", "APPROVED_LEAVE", "Approved leave overlaps this date", "Confirm leave classification/pay treatment."))
                if actual and not int(actual.get("is_absent") or 0) and not actual.get("actual_out"):
                    flags.append(_flag("warning", "MISSING_TIME_OUT", "Actual has missing time-out", "Fill time-out or mark as needs correction."))
                if "halfday" in notes or "half day" in notes:
                    flags.append(_flag("warning", "HALFDAY_REMARK", "Manual log says halfday", "Approve halfday or correct actual hours."))
                if schedule and actual and actual_in is not None and schedule_start is not None and actual_in > schedule_start + 5:
                    flags.append(_flag("warning", "LATE_IN", "Actual time-in is later than schedule", "Verify late/grace/partial absence status."))
                if schedule and actual and actual_out is not None and schedule_end is not None and actual_out < schedule_end - 5:
                    flags.append(_flag("warning", "EARLY_OUT", "Actual time-out is earlier than schedule", "Verify early out, undertime, or halfday."))
                if schedule_minutes and actual_work_minutes is not None and schedule_minutes >= 360 and actual_work_minutes <= schedule_minutes / 2:
                    flags.append(_flag("warning", "HALFDAY_CANDIDATE", "Actual hours are half or less than scheduled hours", "Review as halfday or undertime."))
                if schedule and actual and actual_out is not None and schedule_end is not None and actual_out > schedule_end + 30:
                    flags.append(_flag("warning", "OT_CANDIDATE", "Actual time-out exceeds schedule by more than 30 minutes", "Approve or reject OT."))
                if actual and actual.get("actual_in") and actual.get("actual_out") and _time_minutes(actual.get("actual_out")) is not None and _time_minutes(actual.get("actual_in")) is not None and _time_minutes(actual.get("actual_out")) <= _time_minutes(actual.get("actual_in")):
                    flags.append(_flag("warning", "OVERNIGHT_REVIEW", "Actual shift crosses midnight", "Confirm next-day time-out handling."))
                if not schedule and not actual and not biometric and not approved_leaves and include_info:
                    flags.append(_flag("info", "NO_SCHEDULE_NO_DATA", "No schedule and no attendance data", "Treat as rest day/no shift unless schedule is missing."))

                if not flags:
                    continue

                severity_rank = {"critical": 3, "warning": 2, "info": 1}
                highest = max(flags, key=lambda flag: severity_rank.get(flag["severity"], 0))["severity"]
                totals[highest] += 1
                totals["rows"] += 1
                rows.append(
                    {
                        "employee_id": employee_id,
                        "employee_code": employee.get("employee_code"),
                        "employee_name": employee.get("full_name"),
                        "department": employee.get("department"),
                        "position": employee.get("position"),
                        "work_date": work_date,
                        "schedule": schedule,
                        "schedule_count": len(schedules),
                        "actual": actual,
                        "manual_log_count": len(manual_logs),
                        "biometric": biometric,
                        "biometric_log_count": len(biometric_logs),
                        "approved_leave_count": len(approved_leaves),
                        "flags": flags,
                        "severity": highest,
                        "review_url": f"/schedule?week_start={work_date}&employee_id={employee_id}",
                    }
                )

        rows.sort(key=lambda row: ({"critical": 0, "warning": 1, "info": 2}.get(row["severity"], 9), row["work_date"], row["employee_name"]))
        return {"ok": True, "period_start": start, "period_end": end, "items": rows, "totals": totals, "mode": "schedule_actual_biometric_payroll_qa", "generated_by": user.get("display_name")}
    finally:
        conn.close()
