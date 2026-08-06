from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.cash_advance_service import ensure_schema, now_iso, recalculate_balance, repayment_history
from api.security import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class AmountCorrectionPayload(BaseModel):
    corrected_amount: float
    correction_reason: str
    reference: str | None = None


class CreditSettlementPayload(BaseModel):
    amount: float
    method: str
    note: str
    reference: str | None = None
    target_cash_advance_id: int | None = None


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cash_advance_credit_settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cash_advance_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            method TEXT NOT NULL,
            reference TEXT,
            note TEXT NOT NULL,
            target_cash_advance_id INTEGER,
            settled_by TEXT NOT NULL,
            settled_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_credit_settlements_advance ON cash_advance_credit_settlements(cash_advance_id,id DESC)")
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
        new_opening = corrected
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


@router.post("/cash-advances/{cash_advance_id}/settle-credit")
def settle_cash_advance_credit(
    cash_advance_id: int,
    payload: CreditSettlementPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_owner(authorization, x_api_key)
    amount = round(float(payload.amount or 0), 2)
    method = str(payload.method or "").strip()
    note = str(payload.note or "").strip()
    allowed_methods = {"Cash payout", "Payroll reimbursement", "Offset another cash advance"}
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Settlement amount must be greater than zero.")
    if method not in allowed_methods:
        raise HTTPException(status_code=422, detail="Settlement method is invalid.")
    if not note:
        raise HTTPException(status_code=422, detail="Settlement note is required.")
    if method == "Offset another cash advance" and not payload.target_cash_advance_id:
        raise HTTPException(status_code=422, detail="Target cash advance is required for an offset settlement.")

    conn = get_conn(DB_PATH)
    try:
        ensure_correction_schema(conn)
        advance = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
        if not advance:
            raise HTTPException(status_code=404, detail="Cash advance not found.")
        credit = round(float(advance.get("overpayment_credit") or 0), 2)
        if credit <= 0:
            raise HTTPException(status_code=409, detail="This cash advance has no employee credit to settle.")
        if amount > credit:
            raise HTTPException(status_code=422, detail="Settlement amount cannot exceed available employee credit.")

        target_id = payload.target_cash_advance_id if method == "Offset another cash advance" else None
        if target_id:
            if int(target_id) == int(cash_advance_id):
                raise HTTPException(status_code=422, detail="Offset target must be a different cash advance.")
            target = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (target_id,))
            if not target:
                raise HTTPException(status_code=404, detail="Target cash advance not found.")
            if int(target["employee_id"]) != int(advance["employee_id"]):
                raise HTTPException(status_code=422, detail="Offset target must belong to the same employee.")
            target_summary = recalculate_balance(conn, int(target_id))
            if amount > round(float(target_summary.get("balance") or 0), 2):
                raise HTTPException(status_code=422, detail="Offset amount cannot exceed the target advance balance.")

        stamp = now_iso()
        display_name = user.get("display_name") or "Owner"
        new_credit = round(max(0.0, credit - amount), 2)

        conn.execute(
            """
            INSERT INTO cash_advance_credit_settlements(
                cash_advance_id,employee_id,amount,method,reference,note,
                target_cash_advance_id,settled_by,settled_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                cash_advance_id,
                int(advance["employee_id"]),
                amount,
                method,
                payload.reference,
                note,
                target_id,
                display_name,
                stamp,
            ),
        )

        if target_id:
            conn.execute(
                """
                INSERT INTO cash_advance_repayments(
                    cash_advance_id,employee_id,repayment_date,payment_date,amount,source,
                    payment_method,method,reference,notes,active,created_by,created_at,updated_by,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(target_id),
                    int(advance["employee_id"]),
                    stamp[:10],
                    stamp[:10],
                    amount,
                    "Credit Offset",
                    "Credit Offset",
                    "Credit Offset",
                    payload.reference,
                    f"Offset from overpayment credit on cash advance #{cash_advance_id}. {note}",
                    1,
                    display_name,
                    stamp,
                    display_name,
                    stamp,
                ),
            )
            recalculate_balance(conn, int(target_id))

        conn.execute(
            "UPDATE cash_advances SET overpayment_credit=?, updated_by=?, updated_at=? WHERE id=?",
            (new_credit, display_name, stamp, cash_advance_id),
        )
        summary = recalculate_balance(conn, cash_advance_id)
        conn.commit()

        item = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,)) or {}
        item.update({
            "remaining_balance": summary["balance"],
            "status": summary["status"],
            "total_repaid": summary["paid"],
            "overpayment_credit": new_credit,
            "repayments": repayment_history(conn, cash_advance_id),
        })
        return {"ok": True, "item": item, "settled_amount": amount, "remaining_credit": new_credit}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/cash-advances/{cash_advance_id}/credit-settlements")
def list_credit_settlements(
    cash_advance_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Credit settlement history requires owner or payroll role.")
    conn = get_conn(DB_PATH)
    try:
        ensure_correction_schema(conn)
        return {"ok": True, "items": fetchall(conn, "SELECT * FROM cash_advance_credit_settlements WHERE cash_advance_id=? ORDER BY id DESC", (cash_advance_id,))}
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
