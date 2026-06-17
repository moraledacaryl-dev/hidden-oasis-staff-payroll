from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.payroll_drafts import must_be_payroll_user
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

ADJUSTMENT_TYPES = {"Earning", "Deduction", "Note"}

class PayrollCorrectionRequest(BaseModel):
    employee_id: int
    adjustment_type: str = Field(default="Earning")
    amount: float = 0
    reason: str = Field(..., min_length=3)
    apply_to_next_run: bool = True


def ensure_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            adjustment_type TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            apply_to_next_run INTEGER NOT NULL DEFAULT 1,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payroll_corrections_run ON payroll_corrections(payroll_run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payroll_corrections_employee ON payroll_corrections(employee_id)")
    conn.commit()


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
        ensure_schema(conn)
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
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Only owner can record payroll corrections.")
    adjustment_type = payload.adjustment_type.strip().title()
    if adjustment_type not in ADJUSTMENT_TYPES:
        raise HTTPException(status_code=422, detail="Correction type must be Earning, Deduction, or Note.")
    if adjustment_type != "Note" and float(payload.amount or 0) == 0:
        raise HTTPException(status_code=422, detail="Amount is required for earning or deduction corrections.")

    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
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
                float(payload.amount or 0),
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
