from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.cash_advance_service import ensure_schema, now_iso, recalculate_balance, require_cash_advance_viewer
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class ManualRepaymentPayload(BaseModel):
    amount: float
    repayment_date: str
    payment_method: str = "Cash"
    reference: str | None = None
    notes: str | None = None


@router.post("/cash-advances/{cash_advance_id}/manual-repayments")
def record_manual_repayment(cash_advance_id: int, payload: ManualRepaymentPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    user = require_cash_advance_viewer(authorization, x_api_key)
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Repayment amount must be greater than zero.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        advance = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
        if not advance:
            raise HTTPException(status_code=404, detail="Cash advance not found.")
        current = recalculate_balance(conn, cash_advance_id)
        if current["status"] == "Cancelled":
            raise HTTPException(status_code=409, detail="Cancelled cash advances cannot receive repayments.")
        if amount > current["balance"]:
            raise HTTPException(status_code=422, detail=f"Repayment cannot exceed the current balance of {current['balance']:.2f}.")
        stamp = now_iso()
        cur = conn.execute("INSERT INTO cash_advance_repayments(cash_advance_id,employee_id,repayment_date,amount,source,payment_method,reference,notes,active,created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?)", (cash_advance_id,int(advance["employee_id"]),payload.repayment_date,amount,"Manual",payload.payment_method,payload.reference,payload.notes,user.get("display_name"),stamp,user.get("display_name"),stamp))
        summary = recalculate_balance(conn, cash_advance_id)
        conn.commit()
        return {"ok": True, "repayment_id": int(cur.lastrowid), "summary": summary}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
