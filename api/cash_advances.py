from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class CashAdvancePayload(BaseModel):
    id: int | None = None
    employee_id: int
    advance_date: str
    amount: float
    reason: str | None = None
    approved_by: str | None = None
    repayment_method: str = "Payroll deduction"
    deduction_per_payroll: float = 0
    remaining_balance: float | None = None
    status: str = "Active"
    notes: str | None = None


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cash_advances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            advance_date TEXT NOT NULL,
            amount REAL NOT NULL,
            reason TEXT,
            approved_by TEXT,
            repayment_method TEXT NOT NULL DEFAULT 'Payroll deduction',
            deduction_per_payroll REAL NOT NULL DEFAULT 0,
            remaining_balance REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Active',
            notes TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_advances_employee ON cash_advances(employee_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_advances_status ON cash_advances(status)")
    conn.commit()


def normalize_status(value: str) -> str:
    status = (value or "Active").strip()
    allowed = {"Active", "Fully Paid", "Cancelled"}
    if status not in allowed:
        raise HTTPException(status_code=422, detail="Invalid cash advance status.")
    return status


@router.get("/cash-advances")
def list_cash_advances(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        items = fetchall(
            conn,
            """
            SELECT ca.*, e.full_name, e.employee_code, e.department, e.position
            FROM cash_advances ca
            LEFT JOIN employees e ON e.id = ca.employee_id
            ORDER BY date(ca.advance_date) DESC, ca.id DESC
            """,
        )
        return {"ok": True, "items": items}
    finally:
        conn.close()


@router.post("/cash-advances")
def save_cash_advance(
    payload: CashAdvancePayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    status = normalize_status(payload.status)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,))
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found.")
        timestamp = now_iso()
        remaining_balance = payload.remaining_balance
        if remaining_balance is None:
            remaining_balance = 0 if status == "Fully Paid" else float(payload.amount or 0)
        if remaining_balance < 0:
            raise HTTPException(status_code=422, detail="Remaining balance cannot be negative.")
        if payload.id:
            existing = fetchone(conn, "SELECT id FROM cash_advances WHERE id=?", (payload.id,))
            if not existing:
                raise HTTPException(status_code=404, detail="Cash advance not found.")
            conn.execute(
                """
                UPDATE cash_advances
                SET employee_id=?, advance_date=?, amount=?, reason=?, approved_by=?, repayment_method=?,
                    deduction_per_payroll=?, remaining_balance=?, status=?, notes=?, updated_by=?, updated_at=?
                WHERE id=?
                """,
                (
                    payload.employee_id,
                    payload.advance_date,
                    float(payload.amount or 0),
                    payload.reason,
                    payload.approved_by,
                    payload.repayment_method,
                    float(payload.deduction_per_payroll or 0),
                    float(remaining_balance),
                    status,
                    payload.notes,
                    user.get("display_name"),
                    timestamp,
                    payload.id,
                ),
            )
            advance_id = payload.id
        else:
            cur = conn.execute(
                """
                INSERT INTO cash_advances(
                    employee_id, advance_date, amount, reason, approved_by, repayment_method,
                    deduction_per_payroll, remaining_balance, status, notes,
                    created_by, created_at, updated_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.employee_id,
                    payload.advance_date,
                    float(payload.amount or 0),
                    payload.reason,
                    payload.approved_by,
                    payload.repayment_method,
                    float(payload.deduction_per_payroll or 0),
                    float(remaining_balance),
                    status,
                    payload.notes,
                    user.get("display_name"),
                    timestamp,
                    user.get("display_name"),
                    timestamp,
                ),
            )
            advance_id = int(cur.lastrowid)
        conn.commit()
        item = fetchone(
            conn,
            """
            SELECT ca.*, e.full_name, e.employee_code, e.department, e.position
            FROM cash_advances ca
            LEFT JOIN employees e ON e.id = ca.employee_id
            WHERE ca.id=?
            """,
            (advance_id,),
        )
        return {"ok": True, "item": item}
    finally:
        conn.close()
