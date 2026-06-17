from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchone, get_conn
from core.payroll_engine import update_payroll_status

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
        try:
            update_payroll_status(
                conn,
                run_id,
                "Paid",
                str(user.get("display_name") or "Owner"),
                payload.reference.strip() if payload.reference else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        updated = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        updated["totals"] = totals(conn, run_id)
        return {"ok": True, "run": updated, "mode": "marked_paid_with_payroll_lifecycle"}
    finally:
        conn.close()
