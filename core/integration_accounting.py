from __future__ import annotations

import json
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any

from core.db import fetchall, fetchone, now_iso, get_setting

EXTERNAL_SOURCE = "hidden_oasis_staff_payroll"


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def build_employee_payload(conn, employee_id: int | None = None) -> dict[str, Any]:
    params: tuple[Any, ...] = ()
    where = ""
    if employee_id is not None:
        where = "WHERE id=?"
        params = (employee_id,)
    employees = fetchall(
        conn,
        f"""
        SELECT id, employee_code, full_name, department, position, employment_type,
               status, supervisor, start_date, regularization_date
        FROM employees {where}
        ORDER BY full_name
        """,
        params,
    )
    return {
        "event_type": "employee.sync",
        "external_source": EXTERNAL_SOURCE,
        "external_id": f"employee-sync:{employee_id or 'all'}:{now_iso()}",
        "generated_at": now_iso(),
        "employees": employees,
        "privacy_note": "Only operational identity fields are exported. Salary, benefits, infractions, memos, payroll details, and personal HR notes stay in Staff/Payroll.",
    }


def build_payroll_run_payload(conn, run_id: int) -> dict[str, Any]:
    run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
    if not run:
        raise ValueError(f"Payroll run {run_id} not found")
    items = fetchall(
        conn,
        """
        SELECT pi.*, e.employee_code, e.full_name, e.department, e.position, e.employment_type
        FROM payroll_items pi
        JOIN employees e ON e.id = pi.employee_id
        WHERE pi.payroll_run_id=?
        ORDER BY e.full_name
        """,
        (run_id,),
    )
    totals = {
        "regular_pay": _money(sum(_money(i.get("regular_pay")) for i in items)),
        "ot_pay": _money(sum(_money(i.get("ot_pay")) for i in items)),
        "night_diff_pay": _money(sum(_money(i.get("night_diff_pay")) for i in items)),
        "holiday_pay": _money(sum(_money(i.get("holiday_pay")) for i in items)),
        "paid_leave_pay": _money(sum(_money(i.get("paid_leave_pay")) for i in items)),
        "freelance_pay": _money(sum(_money(i.get("freelance_pay")) for i in items)),
        "other_earnings": _money(sum(_money(i.get("other_earnings")) for i in items)),
        "gross_pay": _money(sum(_money(i.get("gross_pay")) for i in items)),
        "sss_ee": _money(sum(_money(i.get("sss_ee")) for i in items)),
        "philhealth_ee": _money(sum(_money(i.get("philhealth_ee")) for i in items)),
        "pagibig_ee": _money(sum(_money(i.get("pagibig_ee")) for i in items)),
        "tax": _money(sum(_money(i.get("tax")) for i in items)),
        "sss_er": _money(sum(_money(i.get("sss_er")) for i in items)),
        "sss_ec": _money(sum(_money(i.get("sss_ec")) for i in items)),
        "philhealth_er": _money(sum(_money(i.get("philhealth_er")) for i in items)),
        "pagibig_er": _money(sum(_money(i.get("pagibig_er")) for i in items)),
        "cash_advance_deduction": _money(sum(_money(i.get("cash_advance_deduction")) for i in items)),
        "other_deductions": _money(sum(_money(i.get("other_deductions")) for i in items)),
        "total_deductions": _money(sum(_money(i.get("total_deductions")) for i in items)),
        "net_pay": _money(sum(_money(i.get("net_pay")) for i in items)),
    }
    journal_preview = [
        {"debit_account": get_setting(conn, "salary_expense_account", "Salaries and Wages Expense"), "credit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "amount": totals["gross_pay"], "memo": "Gross payroll"},
        {"debit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "credit_account": "SSS Payable", "amount": totals["sss_ee"], "memo": "Employee SSS deduction"},
        {"debit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "credit_account": "PhilHealth Payable", "amount": totals["philhealth_ee"], "memo": "Employee PhilHealth deduction"},
        {"debit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "credit_account": "Pag-IBIG Payable", "amount": totals["pagibig_ee"], "memo": "Employee Pag-IBIG deduction"},
        {"debit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "credit_account": "Withholding Tax Payable", "amount": totals["tax"], "memo": "Employee withholding tax deduction"},
        {"debit_account": get_setting(conn, "employer_contribution_expense_account", "Employer Contributions Expense"), "credit_account": "SSS Payable", "amount": _money(totals["sss_er"] + totals["sss_ec"]), "memo": "Employer SSS/EC"},
        {"debit_account": get_setting(conn, "employer_contribution_expense_account", "Employer Contributions Expense"), "credit_account": "PhilHealth Payable", "amount": totals["philhealth_er"], "memo": "Employer PhilHealth"},
        {"debit_account": get_setting(conn, "employer_contribution_expense_account", "Employer Contributions Expense"), "credit_account": "Pag-IBIG Payable", "amount": totals["pagibig_er"], "memo": "Employer Pag-IBIG"},
        {"debit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "credit_account": get_setting(conn, "employee_ca_account", "Employee Cash Advance Receivable"), "amount": totals["cash_advance_deduction"], "memo": "Cash advance repayment"},
        {"debit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "credit_account": get_setting(conn, "payroll_cash_account", "Payroll Bank / Cash"), "amount": totals["net_pay"], "memo": "Net pay release"},
    ]
    return {
        "event_type": "payroll.run.paid" if run.get("status") in ("Paid", "Locked") else "payroll.run.approved",
        "external_source": EXTERNAL_SOURCE,
        "external_id": f"payroll-run:{run_id}:{run.get('status')}",
        "generated_at": now_iso(),
        "run": {k: run[k] for k in run.keys()},
        "totals": totals,
        "items": items,
        "journal_preview": [j for j in journal_preview if _money(j["amount"]) > 0],
        "receiver_instruction": "Create accounting review-queue records first. Do not silently post final books unless Accounting user approves.",
    }


def build_13th_month_payload(conn, run_id: int) -> dict[str, Any]:
    run = fetchone(conn, "SELECT * FROM payroll_13th_month_runs WHERE id=?", (run_id,))
    if not run:
        raise ValueError(f"13th month run {run_id} not found")
    emp = fetchone(conn, "SELECT employee_code, full_name, department, position FROM employees WHERE id=?", (run["employee_id"],))
    lines = fetchall(conn, "SELECT * FROM payroll_13th_month_lines WHERE run_id=? ORDER BY sort_order", (run_id,))
    return {
        "event_type": "payroll.13th_month.paid",
        "external_source": EXTERNAL_SOURCE,
        "external_id": f"13th-month:{run_id}:{run.get('status')}",
        "generated_at": now_iso(),
        "employee": emp,
        "run": run,
        "lines": lines,
        "journal_preview": [
            {"debit_account": "13th Month Pay Expense", "credit_account": get_setting(conn, "payroll_cash_account", "Payroll Bank / Cash"), "amount": _money(run.get("net_13th_pay")), "memo": f"13th month pay {run.get('year')} - {emp.get('full_name') if emp else ''}"}
        ],
    }


def build_cash_advance_release_payload(conn, cash_advance_id: int) -> dict[str, Any]:
    ca = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
    if not ca:
        raise ValueError(f"Cash advance {cash_advance_id} not found")
    emp = fetchone(conn, "SELECT employee_code, full_name, department, position FROM employees WHERE id=?", (ca["employee_id"],))
    drawer = fetchone(conn, "SELECT * FROM cash_drawer_movements WHERE id=?", (ca.get("drawer_movement_id"),)) if ca.get("drawer_movement_id") else None
    credit = get_setting(conn, "drawer_cash_account", "Cash in Drawer") if ca.get("release_method") == "Cash Drawer" else ca.get("release_method") or "Cash / Bank"
    return {
        "event_type": "cash_advance.released",
        "external_source": EXTERNAL_SOURCE,
        "external_id": f"cash-advance-release:{cash_advance_id}",
        "generated_at": now_iso(),
        "employee": emp,
        "cash_advance": ca,
        "drawer_movement": drawer,
        "journal_preview": [
            {"debit_account": get_setting(conn, "employee_ca_account", "Employee Cash Advance Receivable"), "credit_account": credit, "amount": _money(ca.get("amount")), "memo": f"Cash advance release - {emp.get('full_name') if emp else ''}"}
        ],
    }


def build_cash_advance_repayment_payload(conn, repayment_id: int) -> dict[str, Any]:
    repayment = fetchone(conn, "SELECT * FROM cash_advance_repayments WHERE id=?", (repayment_id,))
    if not repayment:
        raise ValueError(f"Cash advance repayment {repayment_id} not found")
    ca = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (repayment["cash_advance_id"],))
    emp = fetchone(conn, "SELECT employee_code, full_name, department, position FROM employees WHERE id=?", (ca["employee_id"],)) if ca else None
    return {
        "event_type": "cash_advance.repaid",
        "external_source": EXTERNAL_SOURCE,
        "external_id": f"cash-advance-repayment:{repayment_id}",
        "generated_at": now_iso(),
        "employee": emp,
        "cash_advance": ca,
        "repayment": repayment,
        "journal_preview": [
            {"debit_account": get_setting(conn, "salary_payable_account", "Salaries Payable"), "credit_account": get_setting(conn, "employee_ca_account", "Employee Cash Advance Receivable"), "amount": _money(repayment.get("amount")), "memo": "Cash advance repayment through payroll"}
        ],
    }


def enqueue_payload(conn, event_type: str, external_id: str, source_type: str, source_id: int | None, payload: dict[str, Any]) -> int:
    payload_json = _json(payload)
    conn.execute(
        """
        INSERT INTO integration_outbox(event_type, external_source, external_id, source_type, source_id, payload_json, status, created_at, updated_at)
        VALUES(?,?,?,?,?,?, 'Ready', ?, ?)
        ON CONFLICT(external_source, external_id) DO UPDATE SET
            payload_json=excluded.payload_json,
            status=CASE WHEN integration_outbox.status='Sent' THEN integration_outbox.status ELSE 'Ready' END,
            updated_at=excluded.updated_at
        """,
        (event_type, EXTERNAL_SOURCE, external_id, source_type, source_id, payload_json, now_iso(), now_iso()),
    )
    conn.commit()
    row = fetchone(conn, "SELECT id FROM integration_outbox WHERE external_source=? AND external_id=?", (EXTERNAL_SOURCE, external_id))
    return int(row["id"])


def enqueue_payroll_run(conn, run_id: int) -> int:
    payload = build_payroll_run_payload(conn, run_id)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "Payroll Run", run_id, payload)


def enqueue_13th_month(conn, run_id: int) -> int:
    payload = build_13th_month_payload(conn, run_id)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "13th Month", run_id, payload)


def enqueue_cash_advance_release(conn, cash_advance_id: int) -> int:
    payload = build_cash_advance_release_payload(conn, cash_advance_id)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "Cash Advance", cash_advance_id, payload)


def enqueue_cash_advance_repayment(conn, repayment_id: int) -> int:
    payload = build_cash_advance_repayment_payload(conn, repayment_id)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "Cash Advance Repayment", repayment_id, payload)


def enqueue_employee_sync(conn) -> int:
    payload = build_employee_payload(conn, None)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "Employees", None, payload)


def export_outbox_zip(conn, status: str | None = None) -> bytes:
    where = ""
    params: tuple[Any, ...] = ()
    if status and status != "All":
        where = "WHERE status=?"
        params = (status,)
    rows = fetchall(conn, f"SELECT * FROM integration_outbox {where} ORDER BY id", params)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = []
        for row in rows:
            event_type = row["event_type"].replace(".", "_")
            filename = f"{row['id']:04d}_{event_type}_{row['external_id'].replace(':','_')}.json"
            zf.writestr(filename, row["payload_json"])
            manifest.append({k: row[k] for k in row.keys() if k != "payload_json"})
        zf.writestr("manifest.json", _json({"generated_at": now_iso(), "count": len(rows), "events": manifest}))
    return buffer.getvalue()


def mark_outbox_status(conn, ids: list[int], status: str, error: str = "") -> None:
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    sent_at = now_iso() if status == "Sent" else None
    conn.execute(
        f"UPDATE integration_outbox SET status=?, sent_at=COALESCE(?, sent_at), last_error=?, updated_at=? WHERE id IN ({placeholders})",
        (status, sent_at, error, now_iso(), *ids),
    )
    conn.commit()
