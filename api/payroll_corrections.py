from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.payroll_drafts import must_be_payroll_user
from core.corrections import ensure_payroll_corrections_schema
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

ADJUSTMENT_TYPES = {"Earning", "Deduction", "Note"}

class PayrollCorrectionRequest(BaseModel):
    employee_id: int
    adjustment_type: str = Field(default="Earning")
    amount: float = 0
    reason: str = Field(..., min_length=3)
    apply_to_next_run: bool = True


class PayrollCorrectionVoidRequest(BaseModel):
    reason: str = Field(..., min_length=3)


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


@router.get("/payroll/runs/{run_id}/corrections")
def list_payroll_corrections(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_payroll_corrections_schema(conn)
        conn.commit()
        run = fetchone(conn, "SELECT id FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        rows = fetchall(
            conn,
            """
            SELECT pc.*, e.full_name AS employee_name, e.department
            FROM payroll_corrections pc
            LEFT JOIN employees e ON e.id = pc.employee_id
            WHERE pc.payroll_run_id=?
            ORDER BY pc.created_at DESC, pc.id DESC
            """,
            (run_id,),
        )
        return {"ok": True, "items": [clean_row(row) for row in rows], "mode": "correction_records_only"}
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/corrections")
def create_payroll_correction(
    run_id: int,
    payload: PayrollCorrectionRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    adjustment_type = payload.adjustment_type.strip().title()
    if adjustment_type not in ADJUSTMENT_TYPES:
        raise HTTPException(status_code=422, detail="Correction type must be Earning, Deduction, or Note.")
    amount = 0.0 if adjustment_type == "Note" else abs(float(payload.amount or 0))
    if adjustment_type != "Note" and amount == 0:
        raise HTTPException(status_code=422, detail="Amount is required for earning or deduction corrections.")

    conn = get_conn(DB_PATH)
    try:
        ensure_payroll_corrections_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        employee = fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,))
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found.")

        status = str(run.get("status") or "")
        if status == "Draft":
            mode = "draft_run_correction_recorded_manual_item_edit_allowed"
        elif status in {"For Owner Review", "Approved"}:
            mode = "locked_run_correction_recorded_reopen_before_direct_edit"
        elif status in {"Paid", "Released"}:
            mode = "paid_run_adjustment_recorded_do_not_overwrite_history"
        else:
            mode = "correction_recorded"

        cur = conn.execute(
            """
            INSERT INTO payroll_corrections
            (payroll_run_id, employee_id, adjustment_type, amount, reason, apply_to_next_run, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload.employee_id,
                adjustment_type,
                amount,
                payload.reason.strip(),
                1 if payload.apply_to_next_run else 0,
                user.get("display_name"),
            ),
        )
        conn.commit()
        correction = fetchone(conn, "SELECT * FROM payroll_corrections WHERE id=?", (int(cur.lastrowid),)) or {}
        return {"ok": True, "correction": clean_row(correction), "mode": mode}
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/corrections/{correction_id}/void")
def void_payroll_correction(
    run_id: int,
    correction_id: int,
    payload: PayrollCorrectionVoidRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_payroll_corrections_schema(conn)
        row = fetchone(conn, "SELECT * FROM payroll_corrections WHERE id=? AND payroll_run_id=?", (correction_id, run_id))
        if not row:
            raise HTTPException(status_code=404, detail="Correction not found.")
        if row.get("status") == "Applied":
            raise HTTPException(status_code=409, detail="Applied corrections cannot be voided here. Record a new correction.")
        if row.get("status") == "Voided":
            raise HTTPException(status_code=409, detail="Correction is already voided.")
        conn.execute(
            """
            UPDATE payroll_corrections
            SET status='Voided', voided_by=?, void_reason=?, voided_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (user.get("display_name"), payload.reason.strip(), correction_id),
        )
        conn.execute(
            "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?, 'Payroll correction voided', 'payroll_corrections', ?, ?, CURRENT_TIMESTAMP)",
            (user.get("display_name"), correction_id, payload.reason.strip()),
        )
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM payroll_corrections WHERE id=?", (correction_id,)) or {}
        return {"ok": True, "correction": clean_row(updated)}
    finally:
        conn.close()
