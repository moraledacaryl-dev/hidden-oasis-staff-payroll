from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.schedule_source import table_columns, table_exists, trusted_schedule_rows

router = APIRouter(prefix="/api/v1")


def employee_name(row: dict[str, Any]) -> str:
    return str(row.get("full_name") or row.get("name") or row.get("employee_name") or "")


def ensure_user_employee_column(conn) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(app_users)").fetchall()}
    if "employee_id" not in columns:
        conn.execute("ALTER TABLE app_users ADD COLUMN employee_id INTEGER")
        conn.commit()


def linked_employee(conn, user: dict[str, Any]) -> dict[str, Any]:
    ensure_user_employee_column(conn)
    account = fetchone(conn, "SELECT employee_id FROM app_users WHERE id=? AND active=1", (user.get("id"),))
    employee_id = int(account.get("employee_id") or 0) if account else 0
    if not employee_id:
        raise HTTPException(status_code=403, detail="Account is not linked to an employee record.")
    employee = fetchone(conn, "SELECT * FROM employees WHERE id=? AND COALESCE(status, 'Active') != 'Inactive'", (employee_id,))
    if not employee:
        raise HTTPException(status_code=403, detail="Linked employee record is inactive or missing.")
    return employee


def payroll_items(conn, employee_id: int) -> list[dict[str, Any]]:
    return fetchall(
        conn,
        """
        SELECT pi.id, pi.payroll_run_id, pi.employee_id,
               pi.regular_hours, pi.approved_ot_hours, pi.night_diff_hours,
               pi.regular_pay, pi.ot_pay, pi.night_diff_pay, pi.holiday_pay,
               pi.paid_leave_pay, pi.freelance_pay, pi.other_earnings, pi.gross_pay,
               pi.sss_ee, pi.philhealth_ee, pi.pagibig_ee, pi.tax,
               pi.cash_advance_deduction, pi.other_deductions, pi.total_deductions,
               pi.net_pay, pr.period_start, pr.period_end, pr.payout_date, pr.run_label, pr.status
        FROM payroll_items pi
        JOIN payroll_runs pr ON pr.id = pi.payroll_run_id
        WHERE pi.employee_id = ? AND pr.status IN ('Approved', 'Paid', 'Released')
        ORDER BY pr.period_end DESC, pr.id DESC
        """,
        (employee_id,),
    )


def recent_time_logs(conn, employee_id: int, today: date) -> list[dict[str, Any]]:
    start = (today - timedelta(days=14)).isoformat()
    end = today.isoformat()
    if not table_exists(conn, "time_logs"):
        return []
    return fetchall(
        conn,
        """
        SELECT id, work_date, actual_in, actual_out, attendance_status,
               is_absent, absence_type, approved_ot_hours, ot_status, notes
        FROM time_logs
        WHERE employee_id=? AND date(work_date) BETWEEN date(?) AND date(?)
        ORDER BY date(work_date) DESC, id DESC
        LIMIT 20
        """,
        (employee_id, start, end),
    )


def leave_balances(conn, employee_id: int, year: int) -> list[dict[str, Any]]:
    if not table_exists(conn, "leave_types") or not table_exists(conn, "employee_leave_entitlements"):
        return []
    rows = fetchall(
        conn,
        """
        SELECT ele.leave_type_id, lt.name AS leave_type_name, ele.credits, ele.used,
               ele.entitled, lt.paid
        FROM employee_leave_entitlements ele
        JOIN leave_types lt ON lt.id=ele.leave_type_id
        WHERE ele.employee_id=? AND ele.year=? AND COALESCE(lt.active, 1)=1
        ORDER BY lt.name
        """,
        (employee_id, year),
    )
    for row in rows:
        used = float(row.get("used") or 0)
        credits = float(row.get("credits") or 0)
        row["remaining"] = max(0.0, credits - used)
    return rows


def leave_requests(conn, employee_id: int) -> list[dict[str, Any]]:
    if not table_exists(conn, "leave_requests"):
        return []
    type_join = "LEFT JOIN leave_types lt ON lt.id=lr.leave_type_id" if table_exists(conn, "leave_types") else ""
    type_expr = "lt.name AS leave_type_name" if type_join else "NULL AS leave_type_name"
    return fetchall(
        conn,
        f"""
        SELECT lr.id, lr.start_date, lr.end_date, lr.days, lr.paid, lr.status,
               lr.reason, lr.reviewed_by, lr.reviewed_at, {type_expr}
        FROM leave_requests lr
        {type_join}
        WHERE lr.employee_id=?
        ORDER BY date(lr.start_date) DESC, lr.id DESC
        LIMIT 20
        """,
        (employee_id,),
    )


def hr_records(conn, employee_id: int) -> list[dict[str, Any]]:
    if not table_exists(conn, "hr_records"):
        return []
    return fetchall(
        conn,
        """
        SELECT id, record_type, record_date, subject, details, severity,
               status, issued_by, rating
        FROM hr_records
        WHERE employee_id=?
        ORDER BY date(record_date) DESC, id DESC
        LIMIT 20
        """,
        (employee_id,),
    )


def cash_advances(conn, employee_id: int) -> list[dict[str, Any]]:
    if not table_exists(conn, "cash_advances"):
        return []
    cols = table_columns(conn, "cash_advances")
    date_expr = "advance_date" if "advance_date" in cols else ("request_date" if "request_date" in cols else ("created_at" if "created_at" in cols else "'1970-01-01'"))
    amount_expr = "amount" if "amount" in cols else "0"
    balance_expr = "remaining_balance" if "remaining_balance" in cols else ("outstanding_balance" if "outstanding_balance" in cols else amount_expr)
    deduction_expr = "deduction_per_payroll" if "deduction_per_payroll" in cols else ("repayment_per_cutoff" if "repayment_per_cutoff" in cols else "0")
    status_expr = "status" if "status" in cols else "'Active'"
    reason_expr = "reason" if "reason" in cols else "NULL"
    notes_expr = "notes" if "notes" in cols else "NULL"
    return fetchall(
        conn,
        f"""
        SELECT id, {date_expr} AS advance_date, {amount_expr} AS amount,
               {deduction_expr} AS deduction_per_payroll,
               {balance_expr} AS remaining_balance,
               {status_expr} AS status, {reason_expr} AS reason, {notes_expr} AS notes
        FROM cash_advances
        WHERE employee_id=?
        ORDER BY date({date_expr}) DESC, id DESC
        LIMIT 20
        """,
        (employee_id,),
    )


@router.get("/me/payroll")
def my_payroll(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    conn = get_conn(DB_PATH)
    try:
        employee = linked_employee(conn, user)
        employee_id = int(employee.get("id"))
        rows = payroll_items(conn, employee_id)
        return {"ok": True, "employee": {"id": employee_id, "name": employee_name(employee), "department": employee.get("department") or employee.get("department_name") or "Unassigned"}, "items": rows}
    finally:
        conn.close()


@router.get("/me/portal")
def my_portal(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    today = date.today()
    schedule_start = today.isoformat()
    schedule_end = (today + timedelta(days=13)).isoformat()
    conn = get_conn(DB_PATH)
    try:
        employee = linked_employee(conn, user)
        employee_id = int(employee.get("id"))
        schedule = trusted_schedule_rows(conn, schedule_start, schedule_end, employee_id)
        payroll = payroll_items(conn, employee_id)
        leaves = leave_balances(conn, employee_id, today.year)
        requests = leave_requests(conn, employee_id)
        advances = cash_advances(conn, employee_id)
        attendance = recent_time_logs(conn, employee_id, today)
        records = hr_records(conn, employee_id)
        active_advances = [item for item in advances if str(item.get("status") or "").lower() not in {"fully paid", "cancelled", "canceled"}]
        return {
            "ok": True,
            "as_of": today.isoformat(),
            "employee": {
                "id": employee_id,
                "employee_code": employee.get("employee_code") or employee.get("code") or "",
                "name": employee_name(employee),
                "department": employee.get("department") or employee.get("department_name") or "Unassigned",
                "position": employee.get("position") or employee.get("role") or "",
                "status": employee.get("status") or "Active",
            },
            "summary": {
                "visible_payslips": len(payroll),
                "upcoming_shifts": len(schedule),
                "recent_time_logs": len(attendance),
                "leave_types": len(leaves),
                "active_cash_advances": len(active_advances),
                "hr_records": len(records),
            },
            "payroll": payroll[:12],
            "schedule": schedule,
            "attendance": attendance,
            "leave_balances": leaves,
            "leave_requests": requests,
            "hr_records": records,
            "cash_advances": advances,
        }
    finally:
        conn.close()
