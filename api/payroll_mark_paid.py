from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

class MarkPaidRequest(BaseModel):
    confirmation: str
    reference: str | None = None

@router.post("/payroll/runs/{run_id}/mark-paid")
def mark_payroll_run_paid(
    run_id: int,
    payload: MarkPaidRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Only owner can mark payroll as paid.")
    if (payload.confirmation or "").strip() != "MARK PAID":
        raise HTTPException(status_code=422, detail="Type MARK PAID to confirm.")
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        if run.get("status") != "Approved":
            raise HTTPException(status_code=409, detail="Only approved payroll runs can be marked paid.")
        existing_paid_at = run.get("paid_at")
        if existing_paid_at:
            raise HTTPException(status_code=409, detail="Payroll run is already marked paid.")
        conn.execute(
            "UPDATE payroll_runs SET status='Paid', paid_at=datetime('now') WHERE id=?",
            (run_id,),
        )
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        updated["totals"] = totals(conn, run_id)
        return {"ok": True, "run": updated, "mode": "marked_paid_record_only_no_money_moved"}
    finally:
        conn.close()
