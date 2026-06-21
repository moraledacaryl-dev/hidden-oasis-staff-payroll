from __future__ import annotations

import json
from core.db import DB_PATH, fetchall, fetchone, get_conn


def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def select_or_null(columns: set[str], name: str, alias: str | None = None) -> str:
    target = alias or name
    return f"pr.{name} AS {target}" if name in columns else f"NULL AS {target}"


def main() -> None:
    conn = get_conn(DB_PATH)
    try:
        employee = fetchone(conn, "SELECT * FROM employees WHERE lower(trim(full_name))='kate irish gumahin'")
        if not employee:
            print(json.dumps({"error": "Kate Irish Gumahin not found"}, indent=2))
            return

        employee_id = int(employee["id"])
        payroll_run_columns = table_columns(conn, "payroll_runs")
        payroll_item_columns = table_columns(conn, "payroll_items")
        repayment_columns = table_columns(conn, "cash_advance_repayments")
        advance_columns = table_columns(conn, "cash_advances")
        adjustment_columns = table_columns(conn, "payroll_item_adjustments") if fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='payroll_item_adjustments'") else set()

        run_selects = [
            "pr.id AS run_id",
            "pr.period_start",
            "pr.period_end",
            "pr.run_label",
            "pr.status",
            select_or_null(payroll_run_columns, "revision_of_run_id"),
            select_or_null(payroll_run_columns, "revision_treatment"),
            select_or_null(payroll_run_columns, "superseded_by_run_id"),
            "pi.id AS payroll_item_id",
            "pi.cash_advance_deduction",
            "pi.other_earnings",
            "pi.other_deductions",
            "pi.total_deductions",
            "pi.gross_pay",
            "pi.net_pay",
        ]
        runs = fetchall(
            conn,
            f"""
            SELECT {', '.join(run_selects)}
            FROM payroll_items pi
            JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
            WHERE pi.employee_id=?
            ORDER BY date(pr.period_start),pr.id
            """,
            (employee_id,),
        )

        adjustments = []
        if adjustment_columns:
            adjustments = fetchall(conn, "SELECT * FROM payroll_item_adjustments WHERE employee_id=? ORDER BY payroll_run_id,id", (employee_id,))

        repayment_employee_filter = "r.employee_id=?" if "employee_id" in repayment_columns else "ca.employee_id=?"
        repayment_join = "LEFT JOIN cash_advances ca ON ca.id=r.cash_advance_id"
        repayments = fetchall(
            conn,
            f"""
            SELECT r.*,pr.period_start,pr.period_end,pr.status AS payroll_status
            FROM cash_advance_repayments r
            {repayment_join}
            LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
            WHERE {repayment_employee_filter}
            ORDER BY COALESCE(r.payroll_run_id,0),r.id
            """,
            (employee_id,),
        )

        advances = fetchall(conn, "SELECT * FROM cash_advances WHERE employee_id=? ORDER BY id", (employee_id,))

        print(json.dumps({
            "database": str(DB_PATH),
            "employee": employee,
            "schema": {
                "payroll_runs": sorted(payroll_run_columns),
                "payroll_items": sorted(payroll_item_columns),
                "payroll_item_adjustments": sorted(adjustment_columns),
                "cash_advance_repayments": sorted(repayment_columns),
                "cash_advances": sorted(advance_columns),
            },
            "payroll_runs": runs,
            "payroll_item_adjustments": adjustments,
            "cash_advance_repayments": repayments,
            "cash_advances": advances,
        }, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
