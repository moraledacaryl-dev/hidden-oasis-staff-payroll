from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user, totals
from core.cash_advance_payroll import (
    apply_payroll_cash_advance_repayments,
    reverse_payroll_cash_advance_repayments,
)
from core.db import DB_PATH, fetchone, get_conn, now_iso
from core.payroll_engine import create_accounting_queue_for_payroll
from core.quality import build_payroll_preflight_checks

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
        if run.get("paid_at"):
            raise HTTPException(status_code=409, detail="Payroll run is already marked paid.")
        checks = build_payroll_preflight_checks(conn, run["period_start"], run["period_end"])
        blockers = [check for check in checks if check.get("severity") == "Blocker"]
        if blockers:
            raise HTTPException(status_code=409, detail=f"Payroll QA has {len(blockers)} blocker(s). Resolve them before marking paid.")

        actor = str(user.get("display_name") or "Owner")
        reference = payload.reference.strip() if payload.reference else None
        paid_at = now_iso()

        revision_of_run_id = int(run.get("revision_of_run_id") or 0)
        if revision_of_run_id:
            original = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (revision_of_run_id,))
            if not original:
                raise HTTPException(status_code=409, detail="Original payroll run for this revision no longer exists.")
            treatment = str(run.get("revision_treatment") or "")
            original_paid = bool(original.get("paid_at")) or original.get("status") in {"Paid", "Locked", "Released"}
            if treatment == "adjust_paid" and not original_paid:
                raise HTTPException(status_code=409, detail="An adjustment revision can only supersede an already paid payroll run.")
            if treatment == "replace_unpaid" and original_paid:
                raise HTTPException(status_code=409, detail="This replacement revision was created before payment, but the original payroll is now paid. Create a paid adjustment revision instead.")
            if treatment not in {"replace_unpaid", "adjust_paid"}:
                raise HTTPException(status_code=409, detail="Payroll revision treatment is missing or invalid.")
            if original.get("superseded_by_run_id") not in (None, run_id):
                raise HTTPException(status_code=409, detail=f"Original payroll run is already superseded by run #{original['superseded_by_run_id']}.")

            if treatment == "adjust_paid":
                reverse_payroll_cash_advance_repayments(
                    conn,
                    revision_of_run_id,
                    actor=actor,
                    reason=f"Superseded by paid payroll revision #{run_id}",
                )
            conn.execute(
                "UPDATE payroll_runs SET superseded_by_run_id=? WHERE id=?",
                (run_id, revision_of_run_id),
            )
            conn.execute(
                "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
                (
                    actor,
                    "Payroll superseded by revision at payment",
                    "payroll_runs",
                    revision_of_run_id,
                    (
                        f"superseded_by_run_id={run_id}; prior cash-advance repayments reversed"
                        if treatment == "adjust_paid"
                        else f"superseded_by_run_id={run_id}; unpaid original replaced before payment"
                    ),
                    paid_at,
                ),
            )

        apply_payroll_cash_advance_repayments(conn, run_id, actor=actor, reference=reference)
        conn.execute("UPDATE payroll_runs SET status='Paid', paid_at=? WHERE id=?", (paid_at, run_id))
        create_accounting_queue_for_payroll(conn, run_id)
        try:
            from core.integration_accounting import enqueue_payroll_run
            enqueue_payroll_run(conn, run_id)
        except Exception as exc:
            conn.execute(
                "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
                (actor, "Payroll integration event creation failed", "payroll_runs", run_id, str(exc), paid_at),
            )
        conn.execute(
            "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
            (actor, "Payroll status changed from Approved to Paid", "payroll_runs", run_id, reference or "", paid_at),
        )
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        updated["totals"] = totals(conn, run_id)
        return {"ok": True, "run": updated, "mode": "marked_paid_with_cash_advance_repayments"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
