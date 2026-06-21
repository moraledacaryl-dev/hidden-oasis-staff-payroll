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
    return require_cash_advance_viewer(authorization, x_api_key)


def require_cash_advance_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Only owner or payroll can edit existing cash advances.")
    return user


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
        "advance_date": "TEXT", "reason": "TEXT", "approved_by": "TEXT",
        "repayment_method": "TEXT NOT NULL DEFAULT 'Payroll deduction'",
        "deduction_per_payroll": "REAL NOT NULL DEFAULT 0",
        "remaining_balance": "REAL NOT NULL DEFAULT 0",
        "status": "TEXT NOT NULL DEFAULT 'Active'", "notes": "TEXT",
        "created_by": "TEXT", "created_at": "TEXT", "updated_by": "TEXT",
        "updated_at": "TEXT", "ledger_opening_balance": "REAL"
    })

    advance_cols = _columns(conn, "cash_advances")
    if "request_date" in advance_cols:
        conn.execute("UPDATE cash_advances SET advance_date=request_date WHERE advance_date IS NULL OR trim(advance_date)='' ")
    if "repayment_per_cutoff" in advance_cols:
        conn.execute("UPDATE cash_advances SET deduction_per_payroll=repayment_per_cutoff WHERE repayment_per_cutoff IS NOT NULL AND COALESCE(deduction_per_payroll,0)=0")
    if "outstanding_balance" in advance_cols:
        conn.execute("UPDATE cash_advances SET ledger_opening_balance=outstanding_balance WHERE ledger_opening_balance IS NULL AND outstanding_balance IS NOT NULL")
    conn.execute("UPDATE cash_advances SET ledger_opening_balance=COALESCE(ledger_opening_balance,remaining_balance,amount,0)")

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
        "cash_advance_id": "INTEGER", "employee_id": "INTEGER",
        "repayment_date": "TEXT", "amount": "REAL NOT NULL DEFAULT 0",
        "source": "TEXT NOT NULL DEFAULT 'Manual'", "payment_method": "TEXT",
        "payroll_run_id": "INTEGER", "payroll_item_id": "INTEGER",
        "reference": "TEXT", "notes": "TEXT",
        "active": "INTEGER NOT NULL DEFAULT 1", "created_by": "TEXT",
        "created_at": "TEXT", "updated_by": "TEXT", "updated_at": "TEXT",
        "reversed_by": "TEXT", "reversed_at": "TEXT", "reversal_reason": "TEXT"
    })
    conn.execute("UPDATE cash_advance_repayments SET active=1 WHERE active IS NULL")
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
          AND (r.source='Manual' OR COALESCE(pr.status,'') IN ('For Owner Review','Reviewed','Approved','Paid','Locked','Released'))
    """, (cash_advance_id,)) or {}
    return round(float(row.get("total") or 0), 2)


def recalculate_balance(conn, cash_advance_id: int) -> dict[str, Any]:
    row = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Cash advance not found.")
    opening = round(float(row.get("ledger_opening_balance") if row.get("ledger_opening_balance") is not None else row.get("remaining_balance") or row.get("amount") or 0), 2)
    new_paid = confirmed_new_repayments(conn, cash_advance_id)
    balance = round(max(0.0, opening - new_paid), 2)
    historical_paid = round(max(0.0, float(row.get("amount") or 0) - opening), 2)
    total_paid = round(historical_paid + new_paid, 2)
    old_status = str(row.get("status") or "")
    status = "Cancelled" if old_status == "Cancelled" else ("Fully Paid" if balance <= 0 else "Active")
    conn.execute("UPDATE cash_advances SET remaining_balance=?,status=?,updated_at=? WHERE id=?", (balance,status,now_iso(),cash_advance_id))
    return {"amount": round(float(row.get("amount") or 0),2), "paid": total_paid, "balance": balance, "status": status}


def repayment_history(conn, cash_advance_id: int) -> list[dict[str, Any]]:
    return fetchall(conn, """
        SELECT r.*,pr.period_start,pr.period_end,pr.status payroll_status
        FROM cash_advance_repayments r
        LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
        WHERE r.cash_advance_id=? AND COALESCE(r.active,1)=1
        ORDER BY date(r.repayment_date) DESC,r.id DESC
    """, (cash_advance_id,))


@router.get("/cash-advances")
def list_cash_advances(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
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
def save_cash_advance(payload: CashAdvancePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_cash_advance_editor(authorization, x_api_key) if payload.id else require_cash_advance_creator(authorization, x_api_key)
    amount = round(float(payload.amount or 0),2)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Cash advance amount must be greater than zero.")
    method = normalize_method(payload.repayment_method)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        stamp = now_iso()
        if payload.id:
            old = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (payload.id,))
            if not old:
                raise HTTPException(status_code=404, detail="Cash advance not found.")
            opening = float(old.get("ledger_opening_balance") if old.get("ledger_opening_balance") is not None else old.get("remaining_balance") or 0)
            adjusted_opening = round(max(0.0, opening + amount - float(old.get("amount") or 0)),2)
            conn.execute("UPDATE cash_advances SET employee_id=?,advance_date=?,amount=?,reason=?,approved_by=?,repayment_method=?,deduction_per_payroll=?,ledger_opening_balance=?,status=?,notes=?,updated_by=?,updated_at=? WHERE id=?", (payload.employee_id,payload.advance_date,amount,payload.reason,payload.approved_by,method,round(float(payload.deduction_per_payroll or 0),2),adjusted_opening,payload.status,payload.notes,user.get("display_name"),stamp,payload.id))
            advance_id = payload.id
        else:
            if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
                raise HTTPException(status_code=404, detail="Employee not found.")
            cur = conn.execute("INSERT INTO cash_advances(employee_id,advance_date,amount,reason,approved_by,repayment_method,deduction_per_payroll,remaining_balance,ledger_opening_balance,status,notes,created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (payload.employee_id,payload.advance_date,amount,payload.reason,payload.approved_by,method,round(float(payload.deduction_per_payroll or 0),2),amount,amount,"Active",payload.notes,user.get("display_name"),stamp,user.get("display_name"),stamp))
            advance_id = int(cur.lastrowid)
        summary = recalculate_balance(conn, advance_id)
        conn.commit()
        item = fetchone(conn, "SELECT ca.*,e.full_name,e.employee_code,e.department,e.position FROM cash_advances ca LEFT JOIN employees e ON e.id=ca.employee_id WHERE ca.id=?", (advance_id,)) or {}
        item.update({"remaining_balance":summary["balance"],"status":summary["status"],"total_repaid":summary["paid"],"repayments":repayment_history(conn,advance_id)})
        return {"ok": True, "item": item}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
