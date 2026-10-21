from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, field_validator

from api.cash_advance_service import calculate_balance, ensure_schema, now_iso, recalculate_balance, require_cash_advance_editor
from core.db import DB_PATH, fetchone, get_conn
from core.integration_accounting import build_cash_advance_repayment_payload
from core.integration_outbox import enqueue_event, ensure_integration_schema
from core.money import money

router = APIRouter(prefix="/api/v1")


class ManualRepaymentPayload(BaseModel):
    amount: float
    repayment_date: str
    payment_method: str
    # Optional for backward-compatible API clients. New UI always sends it.
    idempotency_key: UUID | None = None
    reference: str | None = None
    notes: str | None = None

    @field_validator("payment_method")
    @classmethod
    def require_explicit_method(cls, value: str) -> str:
        method = str(value or "").strip()
        if not method:
            raise ValueError("Choose the actual repayment method; do not assume Cash.")
        # This endpoint records money received outside payroll. A salary
        # deduction must be created by payroll itself; accepting that method
        # here could reduce an advance without a matching cash receipt or
        # an approved payroll deduction.
        normalized = " ".join(method.lower().replace("-", " ").replace("_", " ").split())
        if normalized in {"payroll deduction", "salary deduction"}:
            raise ValueError("Payroll deductions cannot be recorded as manual repayments.")
        return method

    @field_validator("amount", mode="before")
    @classmethod
    def quantize_amount(cls, value: Any) -> float:
        # Decimal('NaN') quantizes to NaN, which can bypass <= 0 and
        # remaining-balance guards. Reject nonfinite and malformed values
        # before they can reach the repayment or accounting ledgers.
        try:
            parsed = Decimal(str(value))
            if not parsed.is_finite():
                raise ValueError("Repayment must have a finite amount.")
            return money(parsed)
        except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
            raise ValueError("Enter a valid finite repayment amount.") from exc


@router.post("/cash-advances/{cash_advance_id}/manual-repayments")
def record_manual_repayment(cash_advance_id: int, payload: ManualRepaymentPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    user = require_cash_advance_editor(authorization, x_api_key)
    amount = money(payload.amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Repayment amount must be greater than zero.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        # Initialize the durable outbox BEFORE opening the payment transaction.
        # Schema initialization commits; doing so after the insert would leave
        # a repayment recorded without its Accounting review event.
        ensure_integration_schema(conn)
        # Serialize the balance check and payment insert against other writers.
        # A second request with the same key waits for the first to commit.
        conn.execute("BEGIN IMMEDIATE")
        request_key = str(payload.idempotency_key) if payload.idempotency_key else None
        if request_key:
            existing = fetchone(
                conn,
                "SELECT * FROM cash_advance_repayments WHERE idempotency_key=?",
                (request_key,),
            )
            if existing:
                same_request = (
                    int(existing["cash_advance_id"]) == cash_advance_id
                    and str(existing.get("source") or "").lower() == "manual"
                    and money(existing.get("amount") or 0) == amount
                    and str(existing.get("repayment_date") or "") == payload.repayment_date
                    and str(existing.get("payment_method") or "").strip() == payload.payment_method
                    and str(existing.get("reference") or "") == str(payload.reference or "")
                    and str(existing.get("notes") or "") == str(payload.notes or "")
                    and int(existing.get("active") if existing.get("active") is not None else 1) == 1
                )
                if not same_request:
                    raise HTTPException(status_code=409, detail="Repayment request ID already used for a different or reversed payment.")
                summary = calculate_balance(conn, cash_advance_id)
                conn.rollback()  # Release the write lock; no new payment is recorded.
                return {
                    "ok": True,
                    "already_recorded": True,
                    "repayment_id": int(existing["id"]),
                    "summary": summary,
                }
        advance = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
        if not advance:
            raise HTTPException(status_code=404, detail="Cash advance not found.")
        current = recalculate_balance(conn, cash_advance_id)
        if current["status"] == "Cancelled":
            raise HTTPException(status_code=409, detail="Cancelled cash advances cannot receive repayments.")
        if amount > current["balance"]:
            raise HTTPException(status_code=422, detail=f"Repayment cannot exceed the current balance of {current['balance']:.2f}.")
        stamp = now_iso()
        cur = conn.execute("""
            INSERT INTO cash_advance_repayments(
                cash_advance_id,
                employee_id,
                payment_date,
                repayment_date,
                amount,
                source,
                method,
                payment_method,
                reference,
                notes,
                idempotency_key,
                active,
                created_by,
                created_at,
                updated_by,
                updated_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)
        """, (
            cash_advance_id,
            int(advance["employee_id"]),
            payload.repayment_date,
            payload.repayment_date,
            amount,
            "Manual",
            payload.payment_method,
            payload.payment_method,
            payload.reference,
            payload.notes,
            request_key,
            user.get("display_name"),
            stamp,
            user.get("display_name"),
            stamp,
        ))
        repayment_id = int(cur.lastrowid)
        summary = recalculate_balance(conn, cash_advance_id)
        event = build_cash_advance_repayment_payload(conn, repayment_id)
        enqueue_event(
            conn,
            destination="accounting",
            event_type=event["event_type"],
            external_source=event["external_source"],
            external_id=event["external_id"],
            source_type="Cash Advance Repayment",
            source_id=repayment_id,
            payload=event,
            schema_ready=True,
        )
        # The repayment, remaining balance, and review event commit together.
        conn.commit()
        return {"ok": True, "already_recorded": False, "repayment_id": repayment_id, "summary": summary}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
