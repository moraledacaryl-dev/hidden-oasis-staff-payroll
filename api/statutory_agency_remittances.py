"""Government agency remittance ledger, separate from employee collections."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.security import ROLE_OWNER, ROLE_PAYROLL, require_roles
from core.db import fetchall
from core.statutory_reconciliation import ContributionMonth, reconcile_months
from decimal import Decimal
from api.main import db_conn

router = APIRouter(prefix="/api/v1")


def ensure_schema(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS statutory_agency_remittances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program TEXT NOT NULL CHECK(program IN ('sss','philhealth','pagibig')),
            contribution_month TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            reference TEXT,
            note TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_key TEXT UNIQUE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_statutory_agency_remittances_month ON statutory_agency_remittances(contribution_month,program)")


class RemittanceRequest(BaseModel):
    program: Literal["sss", "philhealth", "pagibig"]
    contribution_month: str
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reference: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=1000)


def valid_month(value: str) -> str:
    try:
        if len(value) != 7 or date.fromisoformat(value + "-01").strftime("%Y-%m") != value:
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Month must be YYYY-MM") from exc
    return value


@router.get("/payroll/benefits/remittances")
def list_remittances(month: str, user: dict = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL))) -> dict:
    month = valid_month(month)
    with db_conn(read_only=True) as conn:
        items = fetchall(conn, """
            SELECT id,program,contribution_month,payment_date,amount,reference,note,
                   created_by,created_at,source_type,source_key
            FROM statutory_agency_remittances WHERE contribution_month=?
            ORDER BY payment_date,id
        """, (month,))
    return {"month": month, "items": items}


@router.post("/payroll/benefits/remittances")
def add_remittance(payload: RemittanceRequest, user: dict = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL))) -> dict:
    month = valid_month(payload.contribution_month)
    with db_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO statutory_agency_remittances
            (program,contribution_month,payment_date,amount,reference,note,created_by,created_at)
            VALUES(?,?,?,?,?,?,?,?)
        """, (payload.program,month,payload.payment_date.isoformat(),float(payload.amount),
              payload.reference.strip() or None,payload.note.strip() or None,
              str(user.get("display_name") or user.get("username") or "authorized user"),
              datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return {"ok": True, "id": cursor.lastrowid}


@router.get("/payroll/benefits/remittance-balances")
def remittance_balances(month: str, user: dict = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL))) -> dict:
    """Agency balances through selected month, excluding superseded payrolls.

    Unpaid draft payroll is excluded from recognized obligations. Negative
    closing balances are unverified accounting credits, not agency credits.
    """
    month = valid_month(month)
    with db_conn(read_only=True) as conn:
        obligations = fetchall(conn, """
            SELECT substr(sm.month_start,1,7) AS month,
                   SUM(COALESCE(sm.sss_ee,0)) AS sss_ee,
                   SUM(COALESCE(sm.sss_er,0)+COALESCE(sm.sss_ec,0)) AS sss_er,
                   SUM(COALESCE(sm.philhealth_ee,0)) AS philhealth_ee,
                   SUM(COALESCE(sm.philhealth_er,0)) AS philhealth_er,
                   SUM(COALESCE(sm.pagibig_ee,0)) AS pagibig_ee,
                   SUM(COALESCE(sm.pagibig_er,0)) AS pagibig_er
            FROM payroll_statutory_months sm
            JOIN payroll_runs pr ON pr.id=sm.payroll_run_id
            WHERE substr(sm.month_start,1,7)<=?
              AND pr.status IN ('Paid','Locked')
              AND COALESCE(pr.superseded_by_run_id,0)=0
            GROUP BY substr(sm.month_start,1,7)
        """, (month,))
        remittances = fetchall(conn, """
            SELECT contribution_month AS month, program, SUM(amount) AS amount
            FROM statutory_agency_remittances
            WHERE contribution_month<=?
            GROUP BY contribution_month,program
        """, (month,))
    dues: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
    for row in obligations:
        dues[row["month"]] = {
            program: (Decimal(str(row[program+"_ee"] or 0)), Decimal(str(row[program+"_er"] or 0)))
            for program in ("sss","philhealth","pagibig")
        }
    paid = {(row["month"],row["program"]): Decimal(str(row["amount"] or 0)) for row in remittances}
    months = sorted(set(dues) | {m for m,_ in paid})
    output = {}
    for program in ("sss","philhealth","pagibig"):
        rows = reconcile_months([
            ContributionMonth(m, *(dues.get(m, {}).get(program, (Decimal("0"),Decimal("0")))), paid.get((m,program),Decimal("0")))
            for m in months
        ])
        output[program] = [
            {"month": r.month, "employee_due": float(r.employee_due),
             "employer_due": float(r.employer_due), "total_due": float(r.total_due),
             "remitted": float(r.remitted), "opening_balance": float(r.opening_balance),
             "closing_balance": float(r.closing_balance)}
            for r in rows
        ]
    return {"through_month":month,"programs":output,"credit_status":"unverified_accounting_credit"}
