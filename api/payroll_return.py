from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

class ReturnDraftRequest(BaseModel):
    reason: str

@router.post("/payroll/runs/{run_id}/reopen")
def return_payroll_run_to_draft(
    run_id: int,
    payload: ReturnDraftRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Only owner can reopen payroll.")
    reason = (payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=422, detail="Reopen reason is required.")
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        if run.get("status") not in {"For Owner Review", "Approved"}:
            raise HTTPException(status_code=409, detail="Only review or approved runs can be reopened.")
        conn.execute(
            "UPDATE payroll_runs SET status='Draft', reopen_reason=?, approved_by=NULL, approved_at=NULL, locked_at=NULL WHERE id=?",
            (reason, run_id),
        )
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        updated["totals"] = totals(conn, run_id)
        return {"ok": True, "run": updated, "mode": "reopened_to_draft_not_released"}
    finally:
        conn.close()
