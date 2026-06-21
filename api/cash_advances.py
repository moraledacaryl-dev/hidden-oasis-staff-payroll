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


class ManualRepaymentPayload(BaseModel):
    amount: float
    repayment_date: str
    payment_method: str = "Cash"
    reference: str | None = None
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


def _table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


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
    columns = _table_columns(conn, "cash_advances")
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

    columns = _table_columns(conn, "cash_advances")
    if "request_date" in columns:
        conn.execute("UPDATE cash_advances SET advance_date=request_date WHERE advance_date IS NULL OR trim(advance_date)='' ")
    if "repayment_per_cutoff" in columns:
        conn.execute("UPDATE cash_advances SET deduction_per_payroll=repayment_per_cutoff WHERE repayment_per_cutoff IS NOT NULL AND COALESCE(deduction_per_payroll,0)=0")
    if "outstanding_balance" in columns:
        conn.execute("UPDATE cash_advances SET remaining_balance=outstanding_balance WHERE outstanding_balance IS NOT NULL AND COALESCE(remaining_balance,0)=0")

    conn.execute(
        """
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
            created_at TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL,
            reversed_by TEXT,
            reversed_at TEXT,
            reversal_reason TEXT
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_payroll_repayment ON cash_advance_repayments(cash_advance_id, payroll_run_id) WHERE payroll_run_id IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_repayments_advance ON cash_advance_repayments(cash_advance_id, active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_advances_employee ON cash_advances(employee_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_advances_status ON cash_advances(status)")
    conn.execute(
        """
        UPDATE cash_advances
        SET advance_date=COALESCE(NULLIF(trim(advance_date),''),created_at,date('now')),
            repayment_method=CASE WHEN lower(COALESCE(repayment_method,'')) LIKE '%manual%' THEN 'Manual repayment' ELSE 'Payroll deduction' END,
            deduction_per_payroll=COALESCE(deduction_per_payroll,0),
            remaining_balance=COALESCE(remaining_balance,amount,0),
            status=CASE WHEN lower(COALESCE(status,'')) IN ('paid','fully paid') THEN 'Fully Paid' WHEN lower(COALESCE(status,''))='cancelled' THEN 'Cancelled' ELSE 'Active' END,
            updated_at=COALESCE(updated_at,created_at,CURRENT_TIMESTAMP)
        """
    )
    conn.commit()


def normalize_status(value: str) -> str:
    text = (value or "Active").strip()
    if text == "Approved":
        text = "Active"
    if text not in {"Active", "Fully Paid", "Cancelled"}:
        raise HTTPException(status_code=422, detail="Invalid cash advance status.")
    return text


def normalize_repayment_method(value: str) -> str:
    text = (value or "Payroll deduction").strip().lower()
    if text in {"manual", "manual repayment"}:
        return "Manual repayment"
    if text in {"payroll", "payroll deduction"}:
        return "Payroll deduction"
    raise HTTPException(status_code=422, detail="Repayment method must be Payroll deduction or Manual repayment.")


def confirmed_repayment_total(conn, cash_advance_id: int) -> float:
    row = fetchone(
        conn,
        """
        SELECT COALESCE(SUM(r.amount),0) total
        FROM cash_advance_repayments r
        LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
        WHERE r.cash_advance_id=? AND r.active=1
          AND (r.source='Manual' OR COALESCE(pr.status,'') IN ('For Owner Review','Reviewed','Approved','Paid','Locked','Released'))
        """,
        (cash_advance_id,),
    ) or {}
    return round(float(row.get("total") or 0), 2)


def recalculate_balance(conn, cash_advance_id: int) -> dict[str, Any]:
    advance = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
    if not advance:
        raise HTTPException(status_code=404, detail="Cash advance not found.")
    paid = confirmed_repayment_total(conn, cash_advance_id)
    amount = round(float(advance.get("amount") or 0), 2)
    balance = round(max(0.0, amount - paid), 2)
    status = "Cancelled" if advance.get("status") == "Cancelled" else ("Fully Paid" if balance <= 0 else "Active")
    conn.execute("UPDATE cash_advances SET remaining_balance=?, status=?, updated_at=? WHERE id=?", (balance, status, now_iso(), cash_advance_id))
    return {"amount": amount, "paid": paid, "balance": balance, "status": status}


def sync_all_balances(conn) -> None:
    ensure_schema(conn)
    for row in fetchall(conn, "SELECT id FROM cash_advances"):
        recalculate_balance(conn, int(row["id"]))
    conn.commit()


def repayment_history(conn, cash_advance_id: int) -> list[dict[str, Any]]:
    return fetchall(
        conn,
        """
        SELECT r.*, pr.period_start, pr.period_end, pr.status payroll_status
        FROM cash_advance_repayments r
        LEFT JOIN payroll_runs pr ON pr.id=r.payroll_run_id
        WHERE r.cash_advance_id=? AND r.active=1
        ORDER BY date(r.repayment_date) DESC, r.id DESC
        """,
        (cash_advance_id,),
    )


@router.get("/cash-advances")
def list_cash_advances(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_cash_advance_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        sync_all_balances(conn)
        items = fetchall(conn, "SELECT ca.*, e.full_name, e.employee_code, e.department, e.position FROM cash_advances ca LEFT JOIN employees e ON e.id=ca.employee_id ORDER BY date(ca.advance_date) DESC, ca.id DESC")
        for item in items:
            item["repayments"] = repayment_history(conn, int(item["id"]))
            item["total_repaid"] = confirmed_repayment_total(conn, int(item["id"]))
        return {"ok": True, "items": items}
    finally:
        conn.close()


@router.post("/cash-advances")
def save_cash_advance(payload: CashAdvancePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_cash_advance_editor(authorization, x_api_key) if payload.id else require_cash_advance_creator(authorization, x_api_key)
    status = normalize_status(payload.status)
    method = normalize_repayment_method(payload.repayment_method)
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Cash advance amount must be greater than zero.")
    deduction = round(float(payload.deduction_per_payroll or 0), 2)
    if deduction < 0:
        raise HTTPException(status_code=422, detail="Payroll deduction cannot be negative.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        ts = now_iso()
        if payload.id:
            existing = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (payload.id,))
            if not existing:
                raise HTTPException(status_code=404, detail="Cash advance not found.")
            paid = confirmed_repayment_total(conn, payload.id)
            if amount < paid:
                raise HTTPException(status_code=422, detail=f"Amount cannot be lower than repayments already recorded ({paid:.2f}).")
            conn.execute("""UPDATE cash_advances SET employee_id=?,advance_date=?,amount=?,reason=?,approved_by=?,repayment_method=?,deduction_per_payroll=?,status=?,notes=?,updated_by=?,updated_at=? WHERE id=?""", (payload.employee_id,payload.advance_date,amount,payload.reason,payload.approved_by,method,deduction,status,payload.notes,user.get("display_name"),ts,payload.id))
            advance_id = payload.id
        else:
            cur = conn.execute("""INSERT INTO cash_advances(employee_id,advance_date,amount,reason,approved_by,repayment_method,deduction_per_payroll,remaining_balance,status,notes,created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (payload.employee_id,payload.advance_date,amount,payload.reason,payload.approved_by,method,deduction,amount,status,payload.notes,user.get("display_name"),ts,user.get("display_name"),ts))
            advance_id = int(cur.lastrowid)
        recalculate_balance(conn, advance_id)
        conn.commit()
        item = fetchone(conn, "SELECT ca.*,e.full_name,e.employee_code,e.department,e.position FROM cash_advances ca LEFT JOIN employees e ON e.id=ca.employee_id WHERE ca.id=?", (advance_id,)) or {}
        item["repayments"] = repayment_history(conn, advance_id)
        return {"ok": True, "item": item}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/cash-advances/{cash_advance_id}/repayments")
def record_manual_repayment(cash_advance_id: int, payload: ManualRepaymentPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
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
        ts = now_iso()
        cur = conn.execute("""INSERT INTO cash_advance_repayments(cash_advance_id,employee_id,repayment_date,amount,source,payment_method,reference,notes,active,created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?)""", (cash_advance_id,int(advance["employee_id"]),payload.repayment_date,amount,"Manual",payload.payment_method,payload.reference,payload.notes,user.get("display_name"),ts,user.get("display_name"),ts))
        summary = recalculate_balance(conn, cash_advance_id)
        conn.commit()
        return {"ok": True, "repayment_id": int(cur.lastrowid), "summary": summary}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
