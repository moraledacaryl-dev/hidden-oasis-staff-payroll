from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from api.cash_advance_service import (
    CashAdvancePayload,
    ensure_schema,
    normalize_method,
    now_iso,
    recalculate_balance,
    repayment_history,
    require_cash_advance_creator,
    require_cash_advance_editor,
    require_cash_advance_viewer,
)
from core.db import DB_PATH, fetchall, fetchone, get_conn
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


def _columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _sync_legacy_fields(conn, advance_id: int, amount: float, deduction: float, balance: float) -> None:
    columns = _columns(conn, "cash_advances")
    assignments: list[str] = []
    values: list[Any] = []

    for column, value in (
        ("amount", amount),
        ("deduction_per_payroll", deduction),
        ("remaining_balance", balance),
        ("ledger_opening_balance", balance),
        ("repayment_per_cutoff", deduction),
        ("outstanding_balance", balance),
    ):
        if column in columns:
            assignments.append(f"{column}=?")
            values.append(round(float(value or 0), 2))

    if assignments:
        values.append(advance_id)
        conn.execute(f"UPDATE cash_advances SET {', '.join(assignments)} WHERE id=?", values)


@router.get("/cash-advances")
def list_cash_advances(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_cash_advance_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        items = fetchall(conn, "SELECT ca.*,e.full_name,e.employee_code,e.department,e.position FROM cash_advances ca LEFT JOIN employees e ON e.id=ca.employee_id ORDER BY date(ca.advance_date) DESC,ca.id DESC")
        for item in items:
            summary = recalculate_balance(conn, int(item["id"]))
            item.update({"remaining_balance":summary["balance"],"status":summary["status"],"total_repaid":summary["paid"]})
            item["repayments"] = repayment_history(conn, int(item["id"]))
        conn.commit()
        return {"ok": True, "items": items}
    finally:
        conn.close()


@router.post("/cash-advances")
def save_cash_advance(
    payload: CashAdvancePayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_cash_advance_editor(authorization, x_api_key) if payload.id else require_cash_advance_creator(authorization, x_api_key)
    amount = round(float(payload.amount or 0), 2)
    deduction = round(float(payload.deduction_per_payroll or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Cash advance amount must be greater than zero.")
    if deduction < 0:
        raise HTTPException(status_code=422, detail="Deduction per payroll cannot be negative.")

    method = normalize_method(payload.repayment_method)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        stamp = now_iso()
        if payload.id:
            old = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (payload.id,))
            if not old:
                raise HTTPException(status_code=404, detail="Cash advance not found.")

            previous_amount = round(float(old.get("amount") or 0), 2)
            previous_opening = round(float(old.get("ledger_opening_balance") if old.get("ledger_opening_balance") is not None else old.get("remaining_balance") or previous_amount), 2)
            paid_to_date = round(max(0.0, previous_amount - previous_opening), 2)
            new_opening = round(max(0.0, amount - paid_to_date), 2)

            conn.execute(
                "UPDATE cash_advances SET employee_id=?,advance_date=?,reason=?,approved_by=?,repayment_method=?,status=?,notes=?,updated_by=?,updated_at=? WHERE id=?",
                (payload.employee_id,payload.advance_date,payload.reason,payload.approved_by,method,payload.status,payload.notes,user.get("display_name"),stamp,payload.id),
            )
            _sync_legacy_fields(conn, int(payload.id), amount, deduction, new_opening)
            advance_id = int(payload.id)
        else:
            if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
                raise HTTPException(status_code=404, detail="Employee not found.")
            cur = conn.execute(
                "INSERT INTO cash_advances(employee_id,advance_date,amount,reason,approved_by,repayment_method,deduction_per_payroll,remaining_balance,ledger_opening_balance,status,notes,created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (payload.employee_id,payload.advance_date,amount,payload.reason,payload.approved_by,method,deduction,amount,amount,"Active",payload.notes,user.get("display_name"),stamp,user.get("display_name"),stamp),
            )
            advance_id = int(cur.lastrowid)
            _sync_legacy_fields(conn, advance_id, amount, deduction, amount)

        summary = recalculate_balance(conn, advance_id)
        _sync_legacy_fields(conn, advance_id, amount, deduction, summary["balance"])
        conn.commit()
        item = fetchone(conn, "SELECT ca.*,e.full_name,e.employee_code,e.department,e.position FROM cash_advances ca LEFT JOIN employees e ON e.id=ca.employee_id WHERE ca.id=?", (advance_id,)) or {}
        item.update({"remaining_balance":summary["balance"],"status":summary["status"],"total_repaid":summary["paid"],"repayments":repayment_history(conn,advance_id)})
        return {"ok": True, "item": item}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
