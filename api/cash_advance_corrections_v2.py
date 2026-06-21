from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.cash_advances_v3 import ensure_schema, now_iso, recalculate_balance, repayment_history
from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class AmountCorrectionPayload(BaseModel):
    corrected_amount: float
    correction_reason: str
    reference: str | None = None


def require_owner(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can correct the cash advance balance basis.")
    return user


def ensure_correction_schema(conn) -> None:
    ensure_schema(conn)
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(cash_advances)")}
    if "overpayment_credit" not in columns:
        conn.execute("ALTER TABLE cash_advances ADD COLUMN overpayment_credit REAL NOT NULL DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cash_advance_amount_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cash_advance_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            old_amount REAL NOT NULL,
            new_amount REAL NOT NULL,
            repayments_applied REAL NOT NULL DEFAULT 0,
            old_remaining_balance REAL NOT NULL DEFAULT 0,
            new_remaining_balance REAL NOT NULL DEFAULT 0,
            overpayment_credit REAL NOT NULL DEFAULT 0,
            correction_reason TEXT NOT NULL,
            reference TEXT,
            corrected_by TEXT NOT NULL,
            corrected_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_amount_corrections_advance ON cash_advance_amount_corrections(cash_advance_id,id DESC)")
    conn.commit()


@router.post("/cash-advances/{cash_advance_id}/correct-amount")
def correct_cash_advance_amount(
    cash_advance_id: int,
    payload: AmountCorrectionPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_owner(authorization, x_api_key)
    corrected = round(float(payload.corrected_amount or 0), 2)
    reason = payload.correction_reason.strip()
    if corrected <= 0:
        raise HTTPException(status_code=422, detail="Corrected amount must be greater than zero.")
    if not reason:
        raise HTTPException(status_code=422, detail="Correction reason is required.")

    conn = get_conn(DB_PATH)
    try:
        ensure_correction_schema(conn)
        advance = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
        if not advance:
            raise HTTPException(status_code=404, detail="Cash advance not found.")

        old_summary = recalculate_balance(conn, cash_advance_id)
        encoded_amount = round(float(advance.get("amount") or 0), 2)
        opening_raw = advance.get("ledger_opening_balance")
        current_basis = round(float(opening_raw if opening_raw is not None else encoded_amount), 2)
        if corrected == current_basis:
            raise HTTPException(status_code=422, detail="Corrected amount is already the current balance basis.")

        total_repaid = round(float(old_summary.get("paid") or 0), 2)
        historical_paid = round(max(0.0, encoded_amount - current_basis), 2)
        new_opening = round(max(0.0, corrected - historical_paid), 2)
        credit = round(max(0.0, total_repaid - corrected), 2)
        stamp = now_iso()

        conn.execute(
            "UPDATE cash_advances SET amount=?,ledger_opening_balance=?,overpayment_credit=?,updated_by=?,updated_at=? WHERE id=?",
            (corrected, new_opening, credit, user.get("display_name"), stamp, cash_advance_id),
        )
        new_summary = recalculate_balance(conn, cash_advance_id)
        conn.execute("""
            INSERT INTO cash_advance_amount_corrections(
                cash_advance_id,employee_id,old_amount,new_amount,repayments_applied,
                old_remaining_balance,new_remaining_balance,overpayment_credit,
                correction_reason,reference,corrected_by,corrected_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cash_advance_id, int(advance["employee_id"]), current_basis, corrected,
            total_repaid, float(old_summary.get("balance") or 0),
            float(new_summary.get("balance") or 0), credit, reason,
            payload.reference, user.get("display_name") or "Owner", stamp,
        ))
        conn.commit()
        item = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,)) or {}
        item.update({
            "remaining_balance": new_summary["balance"],
            "status": new_summary["status"],
            "total_repaid": new_summary["paid"],
            "repayments": repayment_history(conn, cash_advance_id),
        })
        return {"ok": True, "item": item, "correction": {
            "old_amount": current_basis,
            "new_amount": corrected,
            "repayments_applied": total_repaid,
            "new_remaining_balance": new_summary["balance"],
            "overpayment_credit": credit,
        }}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/cash-advances/{cash_advance_id}/amount-corrections")
def list_amount_corrections(
    cash_advance_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Amount correction history requires owner or payroll role.")
    conn = get_conn(DB_PATH)
    try:
        ensure_correction_schema(conn)
        return {"ok": True, "items": fetchall(conn, "SELECT * FROM cash_advance_amount_corrections WHERE cash_advance_id=? ORDER BY id DESC", (cash_advance_id,))}
    finally:
        conn.close()
