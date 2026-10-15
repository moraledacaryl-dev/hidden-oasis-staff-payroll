"""Government agency remittance ledger, separate from employee collections."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.security import ROLE_OWNER, ROLE_PAYROLL, require_roles
from core.db import fetchall
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
    amount: float = Field(gt=0)
    reference: str = ""
    note: str = ""


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
        """, (payload.program,month,payload.payment_date.isoformat(),round(payload.amount,2),
              payload.reference.strip() or None,payload.note.strip() or None,
              str(user.get("display_name") or user.get("username") or "authorized user"),
              datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return {"ok": True, "id": cursor.lastrowid}
