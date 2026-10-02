from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from api.payroll_drafts import must_be_payroll_user
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.money import money

router = APIRouter(prefix="/api/v1")
PROGRAM_COLUMNS = {"philhealth": "philhealth_ee", "pagibig": "pagibig_ee"}
PROGRAM_LABELS = {"philhealth": "PhilHealth", "pagibig": "Pag-IBIG"}


def ensure_statutory_settlement_schema(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS statutory_employee_settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            program TEXT NOT NULL CHECK(program IN ('philhealth','pagibig')),
            contribution_month TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            collection_method TEXT NOT NULL CHECK(collection_method IN ('payroll_catchup','outside_payment')),
            payroll_run_id INTEGER REFERENCES payroll_runs(id) ON DELETE CASCADE,
            payment_date TEXT,
            reference TEXT,
            note TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(employee_id, program, contribution_month, collection_method, payroll_run_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_statutory_settlement_month ON statutory_employee_settlements(contribution_month, employee_id, program)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_statutory_settlement_run ON statutory_employee_settlements(payroll_run_id, employee_id)")


def _month_start(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = date.fromisoformat(raw + "-01" if len(raw) == 7 else raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Contribution month must be YYYY-MM.") from exc
    return parsed.replace(day=1).isoformat()


def _program(value: str) -> str:
    program = str(value or "").strip().lower()
    if program not in PROGRAM_COLUMNS:
        raise HTTPException(status_code=422, detail="Program must be PhilHealth or Pag-IBIG.")
    return program


def _obligation(conn: Any, employee_id: int, program: str, month_start: str) -> float:
    column = PROGRAM_COLUMNS[program]
    row = fetchone(conn, f"""
        SELECT COALESCE(SUM(sm.{column}),0) AS amount
        FROM payroll_statutory_months sm
        JOIN payroll_runs pr ON pr.id=sm.payroll_run_id
        WHERE sm.employee_id=? AND sm.month_start=?
          AND pr.status IN ('For Owner Review','Reviewed','Approved','Paid','Locked')
          AND COALESCE(pr.superseded_by_run_id,0)=0
    """, (employee_id, month_start))
    return money((row or {}).get("amount") or 0)


def _settled_amount(conn: Any, employee_id: int, program: str, month_start: str, *, exclude_id: int | None = None) -> float:
    params: list[Any] = [employee_id, program, month_start]
    exclude = ""
    if exclude_id:
        exclude = " AND s.id<>?"
        params.append(exclude_id)
    row = fetchone(conn, f"""
        SELECT COALESCE(SUM(s.amount),0) AS amount
        FROM statutory_employee_settlements s
        LEFT JOIN payroll_runs pr ON pr.id=s.payroll_run_id
        WHERE s.employee_id=? AND s.program=? AND s.contribution_month=?
          {exclude}
          AND (
            s.collection_method='outside_payment'
            OR (s.collection_method='payroll_catchup' AND COALESCE(pr.superseded_by_run_id,0)=0)
          )
    """, params)
    explicit = money((row or {}).get("amount") or 0)
    column = PROGRAM_COLUMNS[program]
    paid = fetchone(conn, f"""
        SELECT COALESCE(SUM(sm.{column}),0) AS amount
        FROM payroll_statutory_months sm
        JOIN payroll_runs pr ON pr.id=sm.payroll_run_id
        WHERE sm.employee_id=? AND sm.month_start=?
          AND pr.status IN ('Paid','Locked')
          AND COALESCE(pr.superseded_by_run_id,0)=0
    """, (employee_id, month_start))
    return money(explicit + float((paid or {}).get("amount") or 0))


def _validate_not_overcollected(conn: Any, employee_id: int, program: str, month_start: str, amount: float, *, exclude_id: int | None = None) -> None:
    obligation = _obligation(conn, employee_id, program, month_start)
    settled = _settled_amount(conn, employee_id, program, month_start, exclude_id=exclude_id)
    if obligation > 0 and money(settled + amount) > money(obligation):
        remaining = money(max(0, obligation - settled))
        raise HTTPException(status_code=409, detail=f"{PROGRAM_LABELS[program]} {month_start[:7]} already has {settled:.2f} recorded against {obligation:.2f} due. Maximum remaining is {remaining:.2f}.")


def catchup_total(conn: Any, run_id: int, employee_id: int) -> float:
    if not fetchone(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='statutory_employee_settlements'"):
        return 0.0
    row = fetchone(conn, """
        SELECT COALESCE(SUM(amount),0) AS amount FROM statutory_employee_settlements
        WHERE payroll_run_id=? AND employee_id=? AND collection_method='payroll_catchup'
    """, (run_id, employee_id))
    return money((row or {}).get("amount") or 0)


def catchup_lines(conn: Any, run_id: int, employee_id: int) -> list[dict[str, Any]]:
    if not fetchone(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='statutory_employee_settlements'"):
        return []
    rows = fetchall(conn, """
        SELECT id, program, contribution_month, amount, note
        FROM statutory_employee_settlements
        WHERE payroll_run_id=? AND employee_id=? AND collection_method='payroll_catchup'
        ORDER BY contribution_month, program
    """, (run_id, employee_id))
    for row in rows:
        row["label"] = f"{PROGRAM_LABELS.get(str(row['program']), str(row['program']))} — {str(row['contribution_month'])[:7]} catch-up"
    return rows


class CatchupPayload(BaseModel):
    program: Literal["philhealth", "pagibig"]
    contribution_month: str
    amount: float = Field(ge=0)
    note: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def quantize(cls, value: Any) -> float:
        return money(value)


class OutsidePaymentPayload(BaseModel):
    employee_id: int
    program: Literal["philhealth", "pagibig"]
    contribution_month: str
    amount: float = Field(gt=0)
    payment_date: date
    reference: str | None = None
    note: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def quantize(cls, value: Any) -> float:
        return money(value)


@router.get("/payroll/runs/{run_id}/employees/{employee_id}/benefit-catchups")
def get_catchups(run_id: int, employee_id: int, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_statutory_settlement_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run or not fetchone(conn, "SELECT id FROM payroll_items WHERE payroll_run_id=? AND employee_id=?", (run_id, employee_id)):
            raise HTTPException(status_code=404, detail="Payroll employee item not found.")
        return {"ok": True, "editable": run.get("status") == "Draft" and run.get("revision_treatment") != "adjust_paid", "items": catchup_lines(conn, run_id, employee_id)}
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/employees/{employee_id}/benefit-catchups")
def save_catchup(run_id: int, employee_id: int, payload: CatchupPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    program = _program(payload.program)
    month_start = _month_start(payload.contribution_month)
    amount = money(payload.amount)
    conn = get_conn(DB_PATH)
    try:
        ensure_statutory_settlement_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        item = fetchone(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=? AND employee_id=?", (run_id, employee_id))
        if not run or not item:
            raise HTTPException(status_code=404, detail="Payroll employee item not found.")
        if run.get("status") != "Draft" or run.get("revision_treatment") == "adjust_paid":
            raise HTTPException(status_code=409, detail="Benefit catch-ups can only be edited on an unpaid Draft payroll.")
        existing = fetchone(conn, """SELECT * FROM statutory_employee_settlements WHERE employee_id=? AND program=? AND contribution_month=? AND collection_method='payroll_catchup' AND payroll_run_id=?""", (employee_id, program, month_start, run_id))
        old_amount = money((existing or {}).get("amount") or 0)
        if amount > 0:
            _validate_not_overcollected(conn, employee_id, program, month_start, amount, exclude_id=int(existing["id"]) if existing else None)
        delta = money(amount - old_amount)
        new_other = money(float(item.get("other_deductions") or 0) + delta)
        new_total = money(float(item.get("total_deductions") or 0) + delta)
        new_net = money(float(item.get("net_pay") or 0) - delta)
        if new_net < 0:
            raise HTTPException(status_code=422, detail="Catch-up would reduce net pay below zero.")
        now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        if amount <= 0:
            if existing:
                conn.execute("DELETE FROM statutory_employee_settlements WHERE id=?", (existing["id"],))
        elif existing:
            conn.execute("UPDATE statutory_employee_settlements SET amount=?, note=?, updated_at=? WHERE id=?", (amount, (payload.note or "").strip() or None, now, existing["id"]))
        else:
            conn.execute("""INSERT INTO statutory_employee_settlements(employee_id,program,contribution_month,amount,collection_method,payroll_run_id,note,created_by,created_at,updated_at) VALUES(?,?,?,?,'payroll_catchup',?,?,?,?,?)""", (employee_id, program, month_start, amount, run_id, (payload.note or "").strip() or None, user.get("display_name"), now, now))
        conn.execute("UPDATE payroll_items SET other_deductions=?, total_deductions=?, net_pay=? WHERE id=?", (new_other, new_total, new_net, item["id"]))
        conn.commit()
        return {"ok": True, "items": catchup_lines(conn, run_id, employee_id), "catchup_total": catchup_total(conn, run_id, employee_id), "net_pay": new_net}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/payroll/benefits/outside-payment")
def record_outside_payment(payload: OutsidePaymentPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    program = _program(payload.program)
    month_start = _month_start(payload.contribution_month)
    amount = money(payload.amount)
    conn = get_conn(DB_PATH)
    try:
        ensure_statutory_settlement_schema(conn)
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        _validate_not_overcollected(conn, payload.employee_id, program, month_start, amount)
        now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        conn.execute("""INSERT INTO statutory_employee_settlements(employee_id,program,contribution_month,amount,collection_method,payment_date,reference,note,created_by,created_at,updated_at) VALUES(?,?,?,?,'outside_payment',?,?,?,?,?,?)""", (payload.employee_id, program, month_start, amount, payload.payment_date.isoformat(), (payload.reference or "").strip() or None, (payload.note or "").strip() or None, user.get("display_name"), now, now))
        conn.commit()
        return {"ok": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
