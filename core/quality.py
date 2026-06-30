from __future__ import annotations

from datetime import datetime, date
from typing import Any
import sqlite3

from .db import fetchall, fetchone, get_setting
from .schedule_source import trusted_scheduled_workdays


def _date_str(v: Any) -> str:
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def build_payroll_preflight_checks(conn: sqlite3.Connection, period_start: str, period_end: str) -> list[dict[str, Any]]:
    """Return payroll QA checks that should be reviewed before saving/approving payroll."""
    checks: list[dict[str, Any]] = []

    def add(severity: str, category: str, issue: str, count: int | float | None = None, action: str = ""):
        checks.append({
            "severity": severity,
            "category": category,
            "issue": issue,
            "count": count if count is not None else "",
            "recommended_action": action,
        })

    pending_logs = fetchone(conn, "SELECT COUNT(*) AS c FROM time_logs WHERE work_date BETWEEN ? AND ? AND attendance_status IN ('Pending','Needs Review','Needs Correction','Needs Manager','Disputed')", (period_start, period_end))["c"]
    if pending_logs:
        add("Blocker", "Attendance", "Attendance review items exist inside the cutoff.", pending_logs, "Resolve them in Attendance before final approval.")

    pending_ot = fetchone(conn, "SELECT COUNT(*) AS c FROM time_logs WHERE work_date BETWEEN ? AND ? AND ot_status='Pending'", (period_start, period_end))["c"]
    if pending_ot:
        add("Blocker", "Overtime", "Pending OT requests exist inside cutoff.", pending_ot, "Approve/reject OT with reason before final payroll.")

    pending_leaves = fetchone(conn, "SELECT COUNT(*) AS c FROM leave_requests WHERE start_date <= ? AND end_date >= ? AND status='Pending'", (period_end, period_start))["c"]
    if pending_leaves:
        add("Warning", "Leaves", "Pending leave requests overlap the cutoff.", pending_leaves, "Approve/reject or classify before payroll approval.")

    missing_logs = 0
    for sched in trusted_scheduled_workdays(conn, period_start, period_end):
        employee_id = int(sched.get("employee_id") or 0)
        work_date = str(sched.get("work_date"))
        log = fetchone(
            conn,
            """
            SELECT id FROM time_logs
            WHERE employee_id=? AND work_date=? AND attendance_status!='Rejected'
            LIMIT 1
            """,
            (employee_id, work_date),
        )
        leave = fetchone(
            conn,
            """
            SELECT id FROM leave_requests
            WHERE employee_id=? AND status='Approved'
              AND start_date<=? AND end_date>=?
            LIMIT 1
            """,
            (employee_id, work_date, work_date),
        )
        if not log and not leave:
            missing_logs += 1
    if missing_logs:
        add("Warning", "Attendance", "Scheduled workdays have no time log and no approved leave.", missing_logs, "These become unpaid absences in payroll; verify if correct.")

    missing_out = fetchone(conn, "SELECT COUNT(*) AS c FROM time_logs WHERE work_date BETWEEN ? AND ? AND is_absent=0 AND (actual_out IS NULL OR actual_out='')", (period_start, period_end))["c"]
    if missing_out:
        add("Warning", "Attendance", "Logs with missing time-out exist.", missing_out, "Correct or mark as rejected/verified before final approval.")

    no_rate = fetchone(conn, "SELECT COUNT(*) AS c FROM employees WHERE status NOT IN ('Inactive','Terminated') AND employment_type!='Freelance' AND COALESCE(hourly_rate,0)<=0", ())["c"]
    if no_rate:
        add("Blocker", "Employee Setup", "Active non-freelance employees have no hourly rate.", no_rate, "Set hourly rate before computing actual-hours payroll.")

    benefits_no_base = fetchone(conn, "SELECT COUNT(*) AS c FROM employees WHERE status NOT IN ('Inactive','Terminated') AND (benefits_philhealth=1 OR benefits_pagibig=1) AND COALESCE(declared_monthly_base,0)<=0", ())["c"]
    if benefits_no_base:
        add("Warning", "Benefits", "Employees with PhilHealth/Pag-IBIG enabled have no declared monthly base.", benefits_no_base, "Set declared monthly base or turn off benefits for that employee.")

    ca_not_released = fetchone(conn, "SELECT COUNT(*) AS c FROM cash_advances WHERE outstanding_balance>0 AND status='Approved'", ())["c"]
    if ca_not_released:
        add("Warning", "Cash Advances", "Approved cash advances are still not marked Released.", ca_not_released, "Only released advances should usually be deducted from payroll.")

    duplicate_runs = fetchone(conn, "SELECT COUNT(*) AS c FROM payroll_runs WHERE period_start=? AND period_end=? AND status IN ('For Owner Review','Reviewed','Approved','Paid','Locked')", (period_start, period_end))["c"]
    if duplicate_runs:
        add("Warning", "Payroll Runs", "There are already reviewed/approved/paid/locked payroll runs for this cutoff.", duplicate_runs, "Do not duplicate contributions; use reopen/replace intentionally.")

    over_leave = fetchone(
        conn,
        """
        SELECT COUNT(*) AS c FROM employee_leave_entitlements
        WHERE entitled=1 AND used > credits + 0.001
        """,
        (),
    )["c"]
    if over_leave:
        add("Warning", "Leaves", "Some employees have used more leave than their configured credits.", over_leave, "Review leave balances and classify excess as unpaid if needed.")

    sss_rows = fetchone(conn, "SELECT COUNT(*) AS c FROM sss_contribution_table WHERE active=1", ())["c"]
    if not sss_rows:
        add("Blocker", "SSS", "No active SSS table rows.", 0, "Import or seed the SSS contribution table.")
    else:
        max_msc = fetchone(conn, "SELECT MAX(msc) AS m FROM sss_contribution_table WHERE active=1", ())["m"]
        if float(max_msc or 0) < 35000:
            add("Warning", "SSS", "Active SSS table max MSC is below ₱35,000.", max_msc, "Validate against the current official table before live payroll.")

    return checks


def summarize_checks(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "No blockers or warnings detected."
    blockers = sum(1 for c in checks if c.get("severity") == "Blocker")
    warnings = sum(1 for c in checks if c.get("severity") == "Warning")
    return f"{blockers} blocker(s), {warnings} warning(s). Review QA checks before approval."
