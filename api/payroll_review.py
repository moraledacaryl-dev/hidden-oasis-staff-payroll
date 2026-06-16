from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

PAYROLL_ITEM_FIELDS = [
    "id", "employee_id", "regular_hours", "regular_pay", "approved_ot_hours", "ot_pay",
    "night_diff_hours", "night_diff_pay", "holiday_pay", "paid_leave_days", "paid_leave_pay",
    "freelance_pay", "other_earnings", "gross_pay", "late_minutes", "undertime_minutes",
    "unpaid_absence_days", "sss_ee", "philhealth_ee", "pagibig_ee", "sss_er", "sss_ec",
    "philhealth_er", "pagibig_er", "tax", "cash_advance_deduction", "other_deductions",
    "total_deductions", "net_pay", "warnings", "created_at",
]

@router.get("/payroll/runs/{run_id}/review")
def review_payroll_run(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        items = fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=? ORDER BY employee_id", (run_id,))
        employees = fetchall(conn, "SELECT * FROM employees")
        employee_by_id = {int(row.get("id")): row for row in employees if row.get("id") is not None}
        normalized_items = []
        for item in items:
            employee = employee_by_id.get(int(item.get("employee_id") or 0), {})
            full_name = employee.get("full_name") or employee.get("name") or employee.get("employee_name") or f"Employee {item.get('employee_id')}"
            row = {field: item.get(field) for field in PAYROLL_ITEM_FIELDS}
            row["employee_name"] = full_name
            row["department"] = employee.get("department") or employee.get("department_name") or "Unassigned"
            row["payroll_run_id"] = run_id
            normalized_items.append(row)
        run["totals"] = totals(conn, run_id)
        return {"ok": True, "run": run, "items": normalized_items, "mode": "review_only_not_released"}
    finally:
        conn.close()
