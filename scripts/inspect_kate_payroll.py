from __future__ import annotations

import json
from core.db import DB_PATH, fetchall, fetchone, get_conn


def main() -> None:
    conn = get_conn(DB_PATH)
    try:
        employee = fetchone(conn, "SELECT * FROM employees WHERE lower(trim(full_name))='kate irish gumahin'")
        if not employee:
            print(json.dumps({"error": "Kate Irish Gumahin not found"}, indent=2))
            return

        employee_id = int(employee["id"])
        runs = fetchall(
            conn,
            """
            SELECT pr.id AS run_id, pr.period_start, pr.period_end, pr.run_label,
                   pr.status, pr.revision_of_run_id, pr.revision_treatment,
                   pi.id AS payroll_item_id, pi.cash_advance_deduction,
                   pi.other_earnings, pi.other_deductions,
                   pi.total_deductions, pi.gross_pay, pi.net_pay
            FROM payroll_items pi
            JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
            WHERE pi.employee_id=?
            ORDER BY date(pr.period_start), pr.id
            """,
            (employee_id,),
        )

        adjustments = fetchall(
            conn,
            "SELECT * FROM payroll_item_adjustments WHERE employee_id=? ORDER BY payroll_run_id,id",
            (employee_id,),
        )
        repayments = fetchall(
            conn,
            """
            SELECT r.*,pr.period_start,pr.period_end,pr.status AS payroll_status
            FROM cash_advance_repayments r
            LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
            WHERE r.employee_id=?
            ORDER BY COALESCE(r.payroll_run_id,0),r.id
            """,
            (employee_id,),
        )
        advances = fetchall(
            conn,
            "SELECT * FROM cash_advances WHERE employee_id=? ORDER BY date(advance_date),id",
            (employee_id,),
        )

        print(json.dumps({
            "database": str(DB_PATH),
            "employee": employee,
            "payroll_runs": runs,
            "payroll_item_adjustments": adjustments,
            "cash_advance_repayments": repayments,
            "cash_advances": advances,
        }, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
