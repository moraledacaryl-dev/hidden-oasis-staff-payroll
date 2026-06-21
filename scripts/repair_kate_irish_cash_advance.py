from __future__ import annotations

import json
from datetime import datetime

from core.db import DB_PATH, fetchall, fetchone, get_conn

TARGET_AMOUNT = 2000.0
TARGET_DEDUCTION = 2000.0
TARGET_NAME = "kate irish gumahin"


def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def main() -> None:
    conn = get_conn(DB_PATH)
    try:
        employee = fetchone(conn, "SELECT * FROM employees WHERE lower(trim(full_name))=?", (TARGET_NAME,))
        if not employee:
            raise RuntimeError("Kate Irish Gumahin not found")
        employee_id = int(employee["id"])

        advances = fetchall(conn, "SELECT * FROM cash_advances WHERE employee_id=? AND status<>'Cancelled' ORDER BY id", (employee_id,))
        if len(advances) != 1:
            raise RuntimeError(f"Expected exactly one active cash advance for Kate Irish Gumahin, found {len(advances)}")
        advance = advances[0]
        advance_id = int(advance["id"])

        ca_columns = table_columns(conn, "cash_advances")
        assignments = []
        values = []
        for column, value in (
            ("amount", TARGET_AMOUNT),
            ("deduction_per_payroll", TARGET_DEDUCTION),
            ("repayment_per_cutoff", TARGET_DEDUCTION),
            ("remaining_balance", TARGET_AMOUNT),
            ("ledger_opening_balance", TARGET_AMOUNT),
            ("outstanding_balance", TARGET_AMOUNT),
            ("custom_next_deduction", None),
        ):
            if column in ca_columns:
                assignments.append(f"{column}=?")
                values.append(value)
        if "updated_at" in ca_columns:
            assignments.append("updated_at=?")
            values.append(datetime.now().replace(microsecond=0).isoformat(sep=" "))
        values.append(advance_id)
        conn.execute(f"UPDATE cash_advances SET {', '.join(assignments)} WHERE id=?", values)

        draft_rows = fetchall(
            conn,
            """
            SELECT pr.id AS run_id,pr.status,pi.*
            FROM payroll_items pi
            JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
            WHERE pi.employee_id=? AND pr.status='Draft'
            ORDER BY pr.id
            """,
            (employee_id,),
        )

        adjustment_table_exists = fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='payroll_item_adjustments'") is not None
        repaired_runs = []
        for item in draft_rows:
            old_cash = round(float(item.get("cash_advance_deduction") or 0), 2)
            if old_cash == TARGET_DEDUCTION:
                new_total = round(float(item.get("total_deductions") or 0), 2)
                new_net = round(float(item.get("net_pay") or 0), 2)
            else:
                new_total = round(float(item.get("total_deductions") or 0) - old_cash + TARGET_DEDUCTION, 2)
                new_net = round(float(item.get("gross_pay") or 0) - new_total, 2)
                conn.execute(
                    "UPDATE payroll_items SET cash_advance_deduction=?,total_deductions=?,net_pay=? WHERE id=?",
                    (TARGET_DEDUCTION,new_total,new_net,item["id"]),
                )

            if adjustment_table_exists:
                now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
                conn.execute(
                    """
                    INSERT INTO payroll_item_adjustments(
                        payroll_run_id,payroll_item_id,employee_id,additional_earning,
                        additional_earning_note,other_deduction,other_deduction_note,
                        cash_advance_id,cash_advance_amount,created_by,created_at,updated_by,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(payroll_run_id,employee_id) DO UPDATE SET
                        cash_advance_id=excluded.cash_advance_id,
                        cash_advance_amount=excluded.cash_advance_amount,
                        updated_by=excluded.updated_by,
                        updated_at=excluded.updated_at
                    """,
                    (item["run_id"],item["id"],employee_id,0,None,0,None,advance_id,TARGET_DEDUCTION,"repair-script",now,"repair-script",now),
                )

            repaired_runs.append({
                "run_id": item["run_id"],
                "old_cash_advance_deduction": old_cash,
                "new_cash_advance_deduction": TARGET_DEDUCTION,
                "new_total_deductions": new_total,
                "new_net_pay": new_net,
            })

        repayment_columns = table_columns(conn, "cash_advance_repayments")
        if repayment_columns:
            conn.execute("DELETE FROM cash_advance_repayments WHERE employee_id=? AND payroll_run_id IN (SELECT id FROM payroll_runs WHERE status='Draft')", (employee_id,))

        conn.commit()
        print(json.dumps({
            "ok": True,
            "database": str(DB_PATH),
            "employee": employee["full_name"],
            "cash_advance_id": advance_id,
            "cash_advance_amount": TARGET_AMOUNT,
            "deduction_per_payroll": TARGET_DEDUCTION,
            "repaired_runs": repaired_runs,
        }, indent=2, default=str))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
