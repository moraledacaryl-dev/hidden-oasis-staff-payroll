from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.payroll_drafts import must_be_payroll_user
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


def table_exists(conn: Any, name: str) -> bool:
    row = fetchone(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return bool(row and int(row.get("c") or 0) > 0)


def event(source: str, title: str, actor: str | None, details: str | None, created_at: str | None, record_id: int | None = None) -> dict[str, Any]:
    return {
        "source": source,
        "title": title,
        "actor": actor or "",
        "details": details or "",
        "created_at": created_at or "",
        "record_id": record_id,
    }


@router.get("/payroll/runs/{run_id}/audit-events")
def payroll_run_audit_events(run_id: int, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")

        events: list[dict[str, Any]] = []
        events.append(event("payroll_runs", "Draft created", run.get("prepared_by"), run.get("validation_summary"), run.get("created_at"), run_id))
        if run.get("locked_at"):
            events.append(event("payroll_runs", "Locked for owner review", run.get("prepared_by"), "Locked for owner review", run.get("locked_at"), run_id))
        if run.get("approved_at"):
            events.append(event("payroll_runs", "Owner approved", run.get("approved_by"), "Payroll run approved", run.get("approved_at"), run_id))
        if run.get("paid_at"):
            events.append(event("payroll_runs", "Marked paid", run.get("approved_by") or run.get("prepared_by"), "Payroll marked paid", run.get("paid_at"), run_id))
        if run.get("reopen_reason"):
            events.append(event("payroll_runs", "Returned to draft", run.get("prepared_by"), run.get("reopen_reason"), run.get("updated_at") or run.get("created_at"), run_id))

        if table_exists(conn, "payroll_corrections"):
            rows = fetchall(conn, "SELECT pc.*, e.full_name AS employee_name FROM payroll_corrections pc LEFT JOIN employees e ON e.id=pc.employee_id WHERE pc.payroll_run_id=? OR pc.applied_to_run_id=? ORDER BY COALESCE(pc.created_at, pc.applied_at) ASC, pc.id ASC", (run_id, run_id))
            for row in rows:
                title = f"Correction {row.get('status') or 'Recorded'}"
                detail = f"{row.get('adjustment_type')} {row.get('amount')}: {row.get('reason')}"
                if row.get("applied_to_run_id") == run_id:
                    title = "Correction applied"
                    detail = f"Correction #{row.get('id')} from run #{row.get('payroll_run_id')} applied to this run. {detail}"
                if row.get("voided_at"):
                    title = "Correction voided"
                    detail = row.get("void_reason") or detail
                events.append(event("payroll_corrections", title, row.get("created_by") or row.get("voided_by"), detail, row.get("applied_at") or row.get("voided_at") or row.get("created_at"), row.get("id")))

        if table_exists(conn, "audit_logs"):
            rows = fetchall(conn, "SELECT * FROM audit_logs WHERE table_name IN ('payroll_runs','payroll_items','payroll_corrections') AND (record_id=? OR details LIKE ?) ORDER BY created_at ASC, id ASC", (run_id, f"%{run_id}%"))
            for row in rows:
                events.append(event("audit_logs", row.get("action") or "Audit log", row.get("actor"), row.get("details"), row.get("created_at"), row.get("id")))

        events.sort(key=lambda item: str(item.get("created_at") or ""))
        return {"ok": True, "items": events, "mode": "payroll_audit_event_stream"}
    finally:
        conn.close()
