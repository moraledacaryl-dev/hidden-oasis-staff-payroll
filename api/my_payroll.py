from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


def employee_name(row: dict[str, Any]) -> str:
    return str(row.get("full_name") or row.get("name") or row.get("employee_name") or "")


def ensure_user_employee_column(conn) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(app_users)").fetchall()}
    if "employee_id" not in columns:
        conn.execute("ALTER TABLE app_users ADD COLUMN employee_id INTEGER")
        conn.commit()


@router.get("/me/payroll")
def my_payroll(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_user_employee_column(conn)
        account = fetchone(conn, "SELECT employee_id FROM app_users WHERE id=? AND active=1", (user.get("id"),))
        employee_id = int(account.get("employee_id") or 0) if account else 0
        if not employee_id:
            raise HTTPException(status_code=403, detail="Account is not linked to an employee record.")
        employee = fetchone(conn, "SELECT * FROM employees WHERE id=? AND COALESCE(status, 'Active') != 'Inactive'", (employee_id,))
        if not employee:
            raise HTTPException(status_code=403, detail="Linked employee record is inactive or missing.")
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
