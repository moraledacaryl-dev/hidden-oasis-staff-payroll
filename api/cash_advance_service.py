from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Header, HTTPException
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from core.db import fetchall, fetchone


class CashAdvancePayload(BaseModel):
    id: int | None = None
    employee_id: int
    advance_date: str
    amount: float
    reason: str | None = None
    approved_by: str | None = None
    repayment_method: str = "Payroll deduction"
    deduction_per_payroll: float = 0
    status: str = "Active"
    notes: str | None = None


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def require_cash_advance_viewer(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    if authorization:
        user = current_user_from_token(authorization)
        if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
            raise HTTPException(status_code=403, detail="Cash advances require owner, payroll, or General Manager access.")
        return user

    require_api_key(x_api_key)
    return {"display_name": "System", "role_key": "payroll"}


def require_cash_advance_creator(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    return require_cash_advance_viewer(authorization, x_api_key)


def require_cash_advance_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    if authorization:
        user = current_user_from_token(authorization)
        if user.get("role_key") not in {"owner", "payroll"}:
            raise HTTPException(status_code=403, detail="Only owner or payroll can edit existing cash advances.")
        return user

    require_api_key(x_api_key)
    return {"display_name": "System", "role_key": "payroll"}


def _columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_missing_columns(conn, table: str, additions: dict[str, str]) -> None:
    current = _columns(conn, table)
    for column, definition in additions.items():
        if column not in current:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema(conn) -> None:
    conn.execute("""
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
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            ledger_opening_balance REAL
        )
    """)
    _add_missing_columns(conn, "cash_advances", {
        "advance_date": "TEXT",
        "request_date": "TEXT",
        "amount": "REAL NOT NULL DEFAULT 0",
        "reason": "TEXT",
        "approved_by": "TEXT",
        "repayment_method": "TEXT NOT NULL DEFAULT 'Payroll deduction'",
        "deduction_per_payroll": "REAL NOT NULL DEFAULT 0",
        "repayment_per_cutoff": "REAL NOT NULL DEFAULT 0",
        "custom_next_deduction": "REAL",
        "remaining_balance": "REAL NOT NULL DEFAULT 0",
        "outstanding_balance": "REAL NOT NULL DEFAULT 0",
        "status": "TEXT NOT NULL DEFAULT 'Active'",
        "notes": "TEXT",
        "created_by": "TEXT",
        "created_at": "TEXT",
        "updated_by": "TEXT",
        "updated_at": "TEXT",
        "ledger_opening_balance": "REAL",
        "approved_by_user_id": "INTEGER",
        "approved_by_name": "TEXT",
        "approved_at": "TEXT",
        "approval_note": "TEXT",
    })

    conn.execute("UPDATE cash_advances SET advance_date=COALESCE(NULLIF(advance_date,''), request_date, date('now'))")
    conn.execute("UPDATE cash_advances SET request_date=COALESCE(NULLIF(request_date,''), advance_date)")
    conn.execute("UPDATE cash_advances SET deduction_per_payroll=repayment_per_cutoff WHERE COALESCE(deduction_per_payroll,0)=0 AND COALESCE(repayment_per_cutoff,0)>0")
    conn.execute("UPDATE cash_advances SET repayment_per_cutoff=deduction_per_payroll WHERE COALESCE(repayment_per_cutoff,0)=0 AND COALESCE(deduction_per_payroll,0)>0")
    conn.execute("UPDATE cash_advances SET ledger_opening_balance=COALESCE(ledger_opening_balance,outstanding_balance,remaining_balance,amount,0)")
    conn.execute("""
        UPDATE cash_advances
           SET approved_by_name=COALESCE(NULLIF(approved_by_name,''), NULLIF(approved_by,''), NULLIF(created_by,''), 'Legacy approved'),
               approved_at=COALESCE(NULLIF(approved_at,''), updated_at, created_at, CURRENT_TIMESTAMP)
         WHERE status IN ('Active','Approved','Partially Paid','Fully Paid')
           AND (approved_at IS NULL OR trim(approved_at)='')
    """)
    conn.execute("UPDATE cash_advances SET remaining_balance=COALESCE(NULLIF(remaining_balance,0), outstanding_balance, amount, 0)")
    conn.execute("UPDATE cash_advances SET outstanding_balance=COALESCE(NULLIF(outstanding_balance,0), remaining_balance, amount, 0)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cash_advance_repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cash_advance_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            repayment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            source TEXT NOT NULL,
            payment_method TEXT,
            payroll_run_id INTEGER,
            payroll_item_id INTEGER,
            reference TEXT,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT,
            created_at TEXT,
            updated_by TEXT,
            updated_at TEXT,
            reversed_by TEXT,
            reversed_at TEXT,
            reversal_reason TEXT
        )
    """)
    _add_missing_columns(conn, "cash_advance_repayments", {
        "cash_advance_id": "INTEGER",
        "employee_id": "INTEGER NOT NULL DEFAULT 0",
        "repayment_date": "TEXT NOT NULL DEFAULT ''",
        "payment_date": "TEXT",
        "amount": "REAL NOT NULL DEFAULT 0",
        "source": "TEXT NOT NULL DEFAULT 'Manual'",
        "payment_method": "TEXT",
        "method": "TEXT",
        "payroll_run_id": "INTEGER",
        "payroll_item_id": "INTEGER",
        "reference": "TEXT",
        "notes": "TEXT",
        "active": "INTEGER NOT NULL DEFAULT 1",
        "created_by": "TEXT",
        "created_at": "TEXT",
        "updated_by": "TEXT",
        "updated_at": "TEXT",
        "reversed_by": "TEXT",
        "reversed_at": "TEXT",
        "reversal_reason": "TEXT",
    })
    conn.execute("UPDATE cash_advance_repayments SET active=1 WHERE active IS NULL")
    conn.execute("UPDATE cash_advance_repayments SET repayment_date=payment_date WHERE (repayment_date IS NULL OR trim(repayment_date)='') AND payment_date IS NOT NULL")
    conn.execute("UPDATE cash_advance_repayments SET payment_date=repayment_date WHERE (payment_date IS NULL OR trim(payment_date)='') AND repayment_date IS NOT NULL")
    conn.execute("UPDATE cash_advance_repayments SET payment_method=method WHERE (payment_method IS NULL OR trim(payment_method)='') AND method IS NOT NULL")
    conn.execute("UPDATE cash_advance_repayments SET method=payment_method WHERE (method IS NULL OR trim(method)='') AND payment_method IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_payroll_repayment ON cash_advance_repayments(cash_advance_id,payroll_run_id) WHERE payroll_run_id IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_repayments_advance ON cash_advance_repayments(cash_advance_id,active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_advances_employee ON cash_advances(employee_id)")
    conn.commit()


def normalize_method(value: str) -> str:
    text = (value or "Payroll deduction").strip().lower()
    if "manual" in text:
        return "Manual repayment"
    if "payroll" in text:
        return "Payroll deduction"
    raise HTTPException(status_code=422, detail="Repayment method must be Payroll deduction or Manual repayment.")


def confirmed_new_repayments(conn, cash_advance_id: int) -> float:
    row = fetchone(conn, """
        SELECT COALESCE(SUM(r.amount),0) total
        FROM cash_advance_repayments r
        LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
        WHERE r.cash_advance_id=? AND COALESCE(r.active,1)=1
          AND (r.source='Manual' OR COALESCE(pr.status,'') IN ('Paid','Locked','Released'))
    """, (cash_advance_id,)) or {}
    return round(float(row.get("total") or 0), 2)


def recalculate_balance(conn, cash_advance_id: int) -> dict[str, Any]:
    row = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Cash advance not found.")
    opening = round(float(row.get("ledger_opening_balance") if row.get("ledger_opening_balance") is not None else row.get("remaining_balance") or row.get("outstanding_balance") or row.get("amount") or 0), 2)
    new_paid = confirmed_new_repayments(conn, cash_advance_id)
    balance = round(max(0.0, opening - new_paid), 2)
    historical_paid = round(max(0.0, float(row.get("amount") or 0) - opening), 2)
    total_paid = round(historical_paid + new_paid, 2)
    old_status = str(row.get("status") or "")
    if old_status == "Cancelled":
        status = "Cancelled"
    elif balance <= 0:
        status = "Fully Paid"
    elif total_paid > 0:
        status = "Partially Paid"
    elif old_status in {"Pending", "Rejected"}:
        status = old_status
    elif old_status == "Approved":
        status = "Approved"
    else:
        status = "Active"
    conn.execute(
        "UPDATE cash_advances SET remaining_balance=?, outstanding_balance=?, status=?, repayment_per_cutoff=COALESCE(NULLIF(repayment_per_cutoff,0), deduction_per_payroll), updated_at=? WHERE id=?",
        (balance, balance, status, now_iso(), cash_advance_id),
    )
    return {"amount": round(float(row.get("amount") or 0),2), "paid": total_paid, "balance": balance, "status": status}


def repayment_history(conn, cash_advance_id: int) -> list[dict[str, Any]]:
    return fetchall(conn, """
        SELECT r.*,pr.period_start,pr.period_end,pr.status payroll_status
        FROM cash_advance_repayments r
        LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
        WHERE r.cash_advance_id=? AND COALESCE(r.active,1)=1
        ORDER BY date(r.repayment_date) DESC,r.id DESC
    """, (cash_advance_id,))
