from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.cash_advances import ensure_schema as ensure_cash_schema, recalculate_balance
from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class AdjustmentPayload(BaseModel):
    additional_earning: float = 0
    additional_earning_note: str | None = None
    other_deduction: float = 0
    other_deduction_note: str | None = None
    cash_advance_id: int | None = None
    cash_advance_amount: float = 0


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def ensure_schema(conn) -> None:
    ensure_cash_schema(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payroll_item_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL,
            payroll_item_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            additional_earning REAL NOT NULL DEFAULT 0,
            additional_earning_note TEXT,
            other_deduction REAL NOT NULL DEFAULT 0,
            other_deduction_note TEXT,
            cash_advance_id INTEGER,
            cash_advance_amount REAL NOT NULL DEFAULT 0,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(payroll_run_id, employee_id)
        )
    """)
    conn.commit()


def reserved_for_other_runs(conn, advance_id: int, run_id: int) -> float:
    row = fetchone(conn, "SELECT COALESCE(SUM(amount),0) total FROM cash_advance_repayments WHERE cash_advance_id=? AND active=1 AND source='Payroll' AND COALESCE(payroll_run_id,0)<>?", (advance_id, run_id)) or {}
    return round(float(row.get("total") or 0), 2)


@router.get("/payroll/runs/{run_id}/employees/{employee_id}/adjustments")
def get_adjustments(run_id: int, employee_id: int, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        item = fetchone(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=? AND employee_id=?", (run_id, employee_id))
        if not run or not item:
            raise HTTPException(status_code=404, detail="Payroll employee item not found.")
        adjustment = fetchone(conn, "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=? AND employee_id=?", (run_id, employee_id)) or {}
        options = []
        for advance in fetchall(conn, "SELECT * FROM cash_advances WHERE employee_id=? AND status<>'Cancelled' ORDER BY date(advance_date),id", (employee_id,)):
            summary = recalculate_balance(conn, int(advance["id"]))
            selected = int(adjustment.get("cash_advance_id") or 0) == int(advance["id"])
            available = summary["balance"] - reserved_for_other_runs(conn, int(advance["id"]), run_id)
            if selected:
                available += float(adjustment.get("cash_advance_amount") or 0)
            if available > 0 or selected:
                options.append({**advance, "available_balance": round(max(0, available), 2)})
        conn.commit()
        return {"ok": True, "run": run, "item": item, "adjustment": adjustment, "cash_advances": options}
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/employees/{employee_id}/adjustments")
def save_adjustments(run_id: int, employee_id: int, payload: AdjustmentPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    earning = round(float(payload.additional_earning or 0), 2)
    other = round(float(payload.other_deduction or 0), 2)
    cash = round(float(payload.cash_advance_amount or 0), 2)
    if min(earning, other, cash) < 0:
        raise HTTPException(status_code=422, detail="Adjustment amounts cannot be negative.")
    if cash and not payload.cash_advance_id:
        raise HTTPException(status_code=422, detail="Select a cash advance.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        item = fetchone(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=? AND employee_id=?", (run_id, employee_id))
        if not run or not item:
            raise HTTPException(status_code=404, detail="Payroll employee item not found.")
        if run.get("status") != "Draft":
            raise HTTPException(status_code=409, detail="Adjustments are editable only while the run is Draft.")
        previous = fetchone(conn, "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=? AND employee_id=?", (run_id, employee_id)) or {}
        old_earning = float(previous.get("additional_earning") or 0)
        old_other = float(previous.get("other_deduction") or 0)
        old_cash = float(previous.get("cash_advance_amount") or 0)
        old_advance = previous.get("cash_advance_id")

        if payload.cash_advance_id:
            advance = fetchone(conn, "SELECT * FROM cash_advances WHERE id=? AND employee_id=?", (payload.cash_advance_id, employee_id))
            if not advance:
                raise HTTPException(status_code=404, detail="Cash advance not found for this employee.")
            available = recalculate_balance(conn, int(payload.cash_advance_id))["balance"] - reserved_for_other_runs(conn, int(payload.cash_advance_id), run_id)
            if old_advance == payload.cash_advance_id:
                available += old_cash
            if cash > round(available, 2):
                raise HTTPException(status_code=422, detail=f"Deduction cannot exceed the available balance of {available:.2f}.")

        gross = round(float(item.get("gross_pay") or 0) - old_earning + earning, 2)
        other_earnings = round(float(item.get("other_earnings") or 0) - old_earning + earning, 2)
        other_deductions = round(float(item.get("other_deductions") or 0) - old_other + other, 2)
        cash_deduction = round(float(item.get("cash_advance_deduction") or 0) - old_cash + cash, 2)
        total_deductions = round(float(item.get("total_deductions") or 0) - old_other - old_cash + other + cash, 2)
        net = round(gross - total_deductions, 2)
        if net < 0:
            raise HTTPException(status_code=422, detail="Adjustments cannot reduce net pay below zero.")
        conn.execute("UPDATE payroll_items SET other_earnings=?,gross_pay=?,cash_advance_deduction=?,other_deductions=?,total_deductions=?,net_pay=? WHERE id=?", (other_earnings,gross,cash_deduction,other_deductions,total_deductions,net,item["id"]))
        ts = now_iso()
        conn.execute("""INSERT INTO payroll_item_adjustments(payroll_run_id,payroll_item_id,employee_id,additional_earning,additional_earning_note,other_deduction,other_deduction_note,cash_advance_id,cash_advance_amount,created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(payroll_run_id,employee_id) DO UPDATE SET additional_earning=excluded.additional_earning,additional_earning_note=excluded.additional_earning_note,other_deduction=excluded.other_deduction,other_deduction_note=excluded.other_deduction_note,cash_advance_id=excluded.cash_advance_id,cash_advance_amount=excluded.cash_advance_amount,updated_by=excluded.updated_by,updated_at=excluded.updated_at""", (run_id,item["id"],employee_id,earning,payload.additional_earning_note,other,payload.other_deduction_note,payload.cash_advance_id,cash,user.get("display_name"),ts,user.get("display_name"),ts))
        if old_advance and old_advance != payload.cash_advance_id:
            conn.execute("UPDATE cash_advance_repayments SET active=0,reversed_by=?,reversed_at=?,reversal_reason='Payroll adjustment changed' WHERE cash_advance_id=? AND payroll_run_id=?", (user.get("display_name"),ts,old_advance,run_id))
        if payload.cash_advance_id and cash > 0:
            conn.execute("""INSERT INTO cash_advance_repayments(cash_advance_id,employee_id,repayment_date,amount,source,payment_method,payroll_run_id,payroll_item_id,active,created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?) ON CONFLICT(cash_advance_id,payroll_run_id) WHERE payroll_run_id IS NOT NULL DO UPDATE SET amount=excluded.amount,payroll_item_id=excluded.payroll_item_id,active=1,updated_by=excluded.updated_by,updated_at=excluded.updated_at,reversed_by=NULL,reversed_at=NULL,reversal_reason=NULL""", (payload.cash_advance_id,employee_id,run.get("payout_date") or run.get("period_end"),cash,"Payroll","Payroll deduction",run_id,item["id"],user.get("display_name"),ts,user.get("display_name"),ts))
        elif old_advance:
            conn.execute("UPDATE cash_advance_repayments SET active=0,reversed_by=?,reversed_at=?,reversal_reason='Removed from payroll draft' WHERE cash_advance_id=? AND payroll_run_id=?", (user.get("display_name"),ts,old_advance,run_id))
        conn.commit()
        return {"ok": True, "item": fetchone(conn, "SELECT * FROM payroll_items WHERE id=?", (item["id"],)), "totals": totals(conn, run_id)}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
