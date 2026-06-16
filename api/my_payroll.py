from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.main import current_user_from_token
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter(prefix="/api/v1")


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def employee_name(row: dict[str, Any]) -> str:
    return str(row.get("full_name") or row.get("name") or row.get("employee_name") or "")


def find_employee(conn, display_name: str) -> dict[str, Any]:
    target = norm(display_name)
    rows = fetchall(conn, "SELECT * FROM employees WHERE COALESCE(status, 'Active') != 'Inactive'")
    exact = [row for row in rows if norm(employee_name(row)) == target]
    if len(exact) == 1:
        return exact[0]
    loose = [row for row in rows if target and (target in norm(employee_name(row)) or norm(employee_name(row)) in target)]
    if len(loose) == 1:
        return loose[0]
    raise HTTPException(status_code=403, detail="Account is not linked to exactly one employee record.")


@router.get("/me/payroll")
def my_payroll(user: dict[str, Any] = Depends(current_user_from_token)) -> dict[str, Any]:
    conn = get_conn(DB_PATH)
    try:
        employee = find_employee(conn, str(user.get("display_name") or ""))
        employee_id = int(employee.get("id"))
        rows = fetchall(
            conn,
            """
            SELECT pi.id, pi.payroll_run_id, pi.employee_id, pi.regular_pay, pi.ot_pay,
                   pi.night_diff_pay, pi.holiday_pay, pi.paid_leave_pay, pi.freelance_pay,
                   pi.other_earnings, pi.gross_pay, pi.sss_ee, pi.philhealth_ee, pi.pagibig_ee,
                   pi.tax, pi.cash_advance_deduction, pi.other_deductions, pi.total_deductions,
                   pi.net_pay, pr.period_start, pr.period_end, pr.payout_date, pr.run_label, pr.status
            FROM payroll_items pi
            JOIN payroll_runs pr ON pr.id = pi.payroll_run_id
            WHERE pi.employee_id = ? AND pr.status IN ('Approved', 'Paid', 'Released')
            ORDER BY pr.period_end DESC, pr.id DESC
            """,
            (employee_id,),
        )
        return {"ok": True, "employee": {"id": employee_id, "name": employee_name(employee), "department": employee.get("department") or employee.get("department_name") or "Unassigned"}, "items": rows}
    finally:
        conn.close()
