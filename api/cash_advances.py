from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
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


def require_cash_advance_viewer(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Cash advances require owner, payroll, or supervisor role.")
    return user


def require_cash_advance_creator(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Only owner, payroll, or supervisor can input cash advances.")
    return user


def require_cash_advance_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Only owner or payroll can edit existing cash advances.")
    return user


def _cash_advance_columns(conn) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(cash_advances)").fetchall()}


def ensure_schema(conn) -> None:
    """Create the current schema and upgrade legacy cash-advance tables in place.

    Older Payroll databases used request_date, repayment_per_cutoff, and
    outstanding_balance. The API now uses advance_date, deduction_per_payroll,
    and remaining_balance. This migration is intentionally idempotent so it can
    safely run whenever the Cash Advances endpoint is opened.
    """
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

    columns = _cash_advance_columns(conn)
    additions = {
        "advance_date": "TEXT",
        "reason": "TEXT",
        "approved_by": "TEXT",
        "repayment_method": "TEXT NOT NULL DEFAULT 'Payroll deduction'",
        "deduction_per_payroll": "REAL NOT NULL DEFAULT 0",
        "remaining_balance": "REAL NOT NULL DEFAULT 0",
        "notes": "TEXT",
        "created_by": "TEXT",
        "created_at": "TEXT",
        "updated_by": "TEXT",
        "updated_at": "TEXT",
    }
    for column, definition in additions.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE cash_advances ADD COLUMN {column} {definition}")

    columns = _cash_advance_columns(conn)
    if "request_date" in columns:
        conn.execute(
            """
            UPDATE cash_advances
            SET advance_date = request_date
            WHERE advance_date IS NULL OR trim(advance_date) = ''
            """
        )
    if "repayment_per_cutoff" in columns:
        conn.execute(
            """
            UPDATE cash_advances
            SET deduction_per_payroll = repayment_per_cutoff
            WHERE repayment_per_cutoff IS NOT NULL
              AND (deduction_per_payroll IS NULL OR deduction_per_payroll = 0)
            """
        )
    if "outstanding_balance" in columns:
        conn.execute(
            """
            UPDATE cash_advances
            SET remaining_balance = outstanding_balance
            WHERE outstanding_balance IS NOT NULL
              AND (remaining_balance IS NULL OR remaining_balance = 0)
            """
        )

    conn.execute(
        """
        UPDATE cash_advances
        SET advance_date = COALESCE(NULLIF(trim(advance_date), ''), created_at, date('now')),
            repayment_method = COALESCE(NULLIF(trim(repayment_method), ''), 'Payroll deduction'),
            deduction_per_payroll = COALESCE(deduction_per_payroll, 0),
            remaining_balance = CASE
                WHEN remaining_balance IS NULL THEN
                    CASE
                        WHEN lower(COALESCE(status, '')) IN ('fully paid', 'paid', 'cancelled') THEN 0
                        ELSE COALESCE(amount, 0)
                    END
                ELSE remaining_balance
            END,
            status = COALESCE(NULLIF(trim(status), ''), 'Active'),
            updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
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
    require_cash_advance_viewer(authorization, x_api_key)
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
    user = require_cash_advance_editor(authorization, x_api_key) if payload.id else require_cash_advance_creator(authorization, x_api_key)
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
