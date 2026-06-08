from __future__ import annotations

from datetime import datetime
import sqlite3

from .db import fetchall, fetchone


def _score_from_rate(rate: float, good_threshold: float, fair_threshold: float) -> int:
    if rate <= good_threshold:
        return 5
    if rate <= fair_threshold:
        return 4
    if rate <= fair_threshold * 1.75:
        return 3
    if rate <= fair_threshold * 2.5:
        return 2
    return 1


def build_annual_review_auto_summary(conn: sqlite3.Connection, employee_id: int, start_date: str, end_date: str) -> dict:
    emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,))
    if not emp:
        return {"summary": "Employee not found.", "scores": {}}

    sched = fetchone(
        conn,
        "SELECT COUNT(*) AS scheduled_days, SUM(CASE WHEN is_rest_day=1 THEN 1 ELSE 0 END) AS rest_days FROM schedules WHERE employee_id=? AND work_date BETWEEN ? AND ?",
        (employee_id, start_date, end_date),
    ) or {}
    logs = fetchone(
        conn,
        """
        SELECT COUNT(*) AS log_count,
               SUM(CASE WHEN attendance_status IN ('Pending','Needs Manager','Disputed') THEN 1 ELSE 0 END) AS pending_logs,
               SUM(late_minutes) AS late_minutes,
               SUM(undertime_minutes) AS undertime_minutes,
               SUM(approved_ot_hours) AS approved_ot_hours,
               SUM(CASE WHEN is_absent=1 THEN 1 ELSE 0 END) AS absent_logs
        FROM time_logs WHERE employee_id=? AND work_date BETWEEN ? AND ?
        """,
        (employee_id, start_date, end_date),
    ) or {}
    infractions = fetchone(
        conn,
        "SELECT COUNT(*) AS c FROM infractions WHERE employee_id=? AND incident_date BETWEEN ? AND ?",
        (employee_id, start_date, end_date),
    ) or {"c": 0}
    memos = fetchone(
        conn,
        "SELECT COUNT(*) AS c FROM memos WHERE employee_id=? AND memo_date BETWEEN ? AND ?",
        (employee_id, start_date, end_date),
    ) or {"c": 0}
    leaves = fetchall(
        conn,
        """
        SELECT lt.name, SUM(lr.days) AS days
        FROM leave_requests lr
        JOIN leave_types lt ON lt.id=lr.leave_type_id
        WHERE lr.employee_id=? AND lr.status='Approved'
          AND lr.start_date <= ? AND lr.end_date >= ?
        GROUP BY lt.name
        ORDER BY lt.name
        """,
        (employee_id, end_date, start_date),
    )
    payroll = fetchone(
        conn,
        """
        SELECT COUNT(DISTINCT pr.id) AS payroll_runs,
               SUM(pi.regular_hours) AS regular_hours,
               SUM(pi.approved_ot_hours) AS payroll_ot_hours,
               SUM(pi.net_pay) AS total_net_pay
        FROM payroll_items pi
        JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
        WHERE pi.employee_id=? AND pr.period_start <= ? AND pr.period_end >= ?
          AND pr.status IN ('Reviewed','Approved','Paid','Locked')
        """,
        (employee_id, end_date, start_date),
    ) or {}

    scheduled_days = int((sched.get("scheduled_days") or 0) - (sched.get("rest_days") or 0))
    log_count = int(logs.get("log_count") or 0)
    pending_logs = int(logs.get("pending_logs") or 0)
    absent_logs = int(logs.get("absent_logs") or 0)
    late_minutes = float(logs.get("late_minutes") or 0)
    undertime_minutes = float(logs.get("undertime_minutes") or 0)
    approved_ot_hours = float(logs.get("approved_ot_hours") or 0)

    late_hours = late_minutes / 60.0
    undertime_hours = undertime_minutes / 60.0
    missing_or_absent_est = max(0, scheduled_days - log_count) + absent_logs
    late_rate = late_hours / max(scheduled_days, 1)
    absence_rate = missing_or_absent_est / max(scheduled_days, 1)
    infraction_count = int(infractions.get("c") or 0)
    memo_count = int(memos.get("c") or 0)

    reliability_score = max(1, 5 - min(4, int(absence_rate * 10) + (1 if pending_logs > 0 else 0)))
    punctuality_score = _score_from_rate(late_rate, 0.05, 0.25)
    policy_score = max(1, 5 - min(4, infraction_count + max(0, memo_count - 1)))
    teamwork_score = 3
    guest_service_score = 3

    leave_text = ", ".join([f"{r['name']}: {float(r['days'] or 0):g} day(s)" for r in leaves]) or "No approved leave recorded"
    summary_lines = [
        f"Auto-summary for {emp.get('full_name')} from {start_date} to {end_date}:",
        f"- Scheduled workdays: {scheduled_days}",
        f"- Time log records: {log_count}; pending/disputed logs: {pending_logs}",
        f"- Estimated missing/absent days: {missing_or_absent_est}",
        f"- Late total: {late_minutes:.0f} minutes ({late_hours:.2f} hours)",
        f"- Undertime total: {undertime_minutes:.0f} minutes ({undertime_hours:.2f} hours)",
        f"- Approved OT from attendance logs: {approved_ot_hours:.2f} hours",
        f"- Approved leaves: {leave_text}",
        f"- Infractions: {infraction_count}; memos: {memo_count}",
        f"- Payroll runs included: {int(payroll.get('payroll_runs') or 0)}; payroll regular hours: {float(payroll.get('regular_hours') or 0):.2f}",
        "",
        "Suggested score starting points:",
        f"- Reliability: {reliability_score}/5",
        f"- Punctuality: {punctuality_score}/5",
        f"- Policy compliance: {policy_score}/5",
        "- Guest service and teamwork should still be manager/supervisor assessed until POS/guest feedback is integrated.",
    ]

    return {
        "summary": "\n".join(summary_lines),
        "scores": {
            "reliability": reliability_score,
            "punctuality": punctuality_score,
            "guest_service": guest_service_score,
            "teamwork": teamwork_score,
            "policy": policy_score,
        },
    }
