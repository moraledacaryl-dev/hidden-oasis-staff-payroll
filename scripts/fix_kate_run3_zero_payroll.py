from __future__ import annotations

import json

from core.db import DB_PATH, fetchall, fetchone, get_conn


def main() -> None:
    conn = get_conn(DB_PATH)
    try:
        employee = fetchone(conn, "SELECT id,full_name FROM employees WHERE lower(trim(full_name))='kate irish gumahin'")
        if not employee:
            raise RuntimeError("Kate Irish Gumahin not found")

        rows = fetchall(
            conn,
            """
            SELECT pr.id AS run_id,pr.period_start,pr.period_end,pr.status,pi.*
            FROM payroll_items pi
            JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
            WHERE pi.employee_id=?
              AND pr.status='Draft'
              AND COALESCE(pi.gross_pay,0)=0
              AND COALESCE(pi.cash_advance_deduction,0)>0
            ORDER BY pr.id
            """,
            (employee["id"],),
        )

        fixed = []
        for row in rows:
            conn.execute(
                "UPDATE payroll_items SET cash_advance_deduction=0,total_deductions=0,net_pay=0 WHERE id=?",
                (row["id"],),
            )
            conn.execute(
                "DELETE FROM payroll_item_adjustments WHERE payroll_run_id=? AND employee_id=?",
                (row["run_id"], employee["id"]),
            )
            conn.execute(
                "DELETE FROM cash_advance_repayments WHERE payroll_run_id=? AND employee_id=?",
                (row["run_id"], employee["id"]),
            )
            fixed.append({
                "run_id": row["run_id"],
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "cash_advance_deduction": 0,
                "total_deductions": 0,
                "net_pay": 0,
            })

        conn.commit()
        print(json.dumps({"ok": True, "employee": employee["full_name"], "fixed_runs": fixed}, indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
