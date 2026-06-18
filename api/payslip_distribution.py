from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn
from api.payroll_drafts import totals
from api.payroll_review import PAYROLL_ITEM_FIELDS, _leave_summaries

router = APIRouter(prefix="/api/v1")

VISIBLE_RUN_STATUSES = {"Approved", "Paid", "Released", "Locked"}


class DistributionPayload(BaseModel):
    method: str = "Printed"
    notes: str | None = None


def require_payslip_user(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Payslip distribution access denied.")
    return user


def ensure_distribution_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payslip_distribution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            distributed_by TEXT,
            distributed_role TEXT,
            distributed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            method TEXT DEFAULT 'Printed',
            notes TEXT,
            UNIQUE(payroll_run_id, employee_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payslip_distribution_run ON payslip_distribution_logs(payroll_run_id)")
    conn.commit()


def get_visible_run(conn, run_id: int) -> dict[str, Any]:
    run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found.")
    if str(run.get("status")) not in VISIBLE_RUN_STATUSES:
        raise HTTPException(status_code=403, detail="Payslips are available only after payroll is approved or paid.")
    return run


@router.get("/payslips/runs")
def list_payslip_runs(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> list[dict[str, Any]]:
    require_payslip_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_distribution_schema(conn)
        rows = fetchall(
            conn,
            """
            SELECT pr.*,
                   COUNT(pi.id) AS employee_count,
                   COUNT(pdl.id) AS distributed_count
            FROM payroll_runs pr
            LEFT JOIN payroll_items pi ON pi.payroll_run_id=pr.id
            LEFT JOIN payslip_distribution_logs pdl ON pdl.payroll_run_id=pr.id AND pdl.employee_id=pi.employee_id
            WHERE pr.status IN ('Approved','Paid','Released','Locked')
            GROUP BY pr.id
            ORDER BY pr.created_at DESC, pr.id DESC
            LIMIT 30
            """,
        )
        for row in rows:
            row["totals"] = totals(conn, int(row["id"]))
        return rows
    finally:
        conn.close()


@router.get("/payslips/runs/{run_id}")
def payslip_run_detail(run_id: int, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_payslip_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_distribution_schema(conn)
        run = get_visible_run(conn, run_id)
        items = fetchall(
            conn,
            """
            SELECT pi.*, e.full_name AS employee_name, e.employee_code, e.department, e.position,
                   pdl.distributed_at, pdl.distributed_by, pdl.method AS distribution_method, pdl.notes AS distribution_notes
            FROM payroll_items pi
            JOIN employees e ON e.id=pi.employee_id
            LEFT JOIN payslip_distribution_logs pdl ON pdl.payroll_run_id=pi.payroll_run_id AND pdl.employee_id=pi.employee_id
            WHERE pi.payroll_run_id=?
            ORDER BY e.department, e.full_name
            """,
            (run_id,),
        )
        normalized = []
        for item in items:
            row = {field: item.get(field) for field in PAYROLL_ITEM_FIELDS}
            row["employee_id"] = item.get("employee_id")
            row["employee_name"] = item.get("employee_name")
            row["employee_code"] = item.get("employee_code")
            row["department"] = item.get("department") or "Unassigned"
            row["position"] = item.get("position")
            row["payroll_run_id"] = run_id
            row["leave_summary"] = _leave_summaries(conn, int(item.get("employee_id") or 0), str(run.get("period_start")), str(run.get("period_end")))
            row["distribution"] = {
                "distributed": bool(item.get("distributed_at")),
                "distributed_at": item.get("distributed_at"),
                "distributed_by": item.get("distributed_by"),
                "method": item.get("distribution_method"),
                "notes": item.get("distribution_notes"),
            }
            normalized.append(row)
        run["totals"] = totals(conn, run_id)
        return {"ok": True, "run": run, "items": normalized}
    finally:
        conn.close()


@router.post("/payslips/runs/{run_id}/employees/{employee_id}/distributed")
def mark_payslip_distributed(run_id: int, employee_id: int, payload: DistributionPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_payslip_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_distribution_schema(conn)
        get_visible_run(conn, run_id)
        if not fetchone(conn, "SELECT id FROM payroll_items WHERE payroll_run_id=? AND employee_id=?", (run_id, employee_id)):
            raise HTTPException(status_code=404, detail="Payslip item not found.")
        conn.execute(
            """
            INSERT INTO payslip_distribution_logs(payroll_run_id, employee_id, distributed_by, distributed_role, distributed_at, method, notes)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(payroll_run_id, employee_id)
            DO UPDATE SET distributed_by=excluded.distributed_by, distributed_role=excluded.distributed_role, distributed_at=CURRENT_TIMESTAMP, method=excluded.method, notes=excluded.notes
            """,
            (run_id, employee_id, user.get("display_name"), user.get("role_key"), payload.method, payload.notes),
        )
        conn.commit()
        return {"ok": True, "message": "Payslip marked as distributed."}
    finally:
        conn.close()
