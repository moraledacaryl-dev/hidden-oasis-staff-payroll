from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.main import require_api_key
from api.staff_self_service import audit, ensure_schema, now_iso, request_row
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1/internal")


class InternalDecisionPayload(BaseModel):
    actor_user_id: int
    decision: str
    decision_note: str | None = None
    employee_notified: bool = False
    coverage_confirmed: bool = False
    apply_change: bool = True


def reviewer(conn, actor_user_id: int) -> dict[str, Any]:
    row = fetchone(conn, "SELECT id, display_name, role, active FROM app_users WHERE id=? AND active=1", (actor_user_id,))
    if not row:
        raise HTTPException(status_code=403, detail="Reviewer account not found.")
    role = str(row.get("role") or "").strip().lower().replace(" ", "_")
    if role not in {"owner", "admin", "administrator", "payroll", "payroll_admin", "hr", "hr_payroll", "supervisor", "manager", "department_head"}:
        raise HTTPException(status_code=403, detail="Management access required.")
    return row


@router.get("/schedule/change-requests")
def internal_change_requests(
    actor_user_id: int = Query(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        reviewer(conn, actor_user_id)
        items = fetchall(
            conn,
            """
            SELECT r.*, e.full_name AS employee_name, e.employee_code, e.department,
                   se.full_name AS swap_employee_name, u.display_name AS reviewed_by_name
            FROM shift_change_requests r
            JOIN employees e ON e.id=r.employee_id
            LEFT JOIN employees se ON se.id=r.proposed_swap_employee_id
            LEFT JOIN app_users u ON u.id=r.reviewed_by_user_id
            ORDER BY CASE r.status WHEN 'Emergency Review' THEN 0 WHEN 'Pending' THEN 1 WHEN 'Swap Confirmation' THEN 2 ELSE 3 END,
                     r.submitted_at DESC
            """,
        )
        return {"ok": True, "items": items}
    finally:
        conn.close()


@router.post("/schedule/change-requests/{request_id}/decision")
def internal_decision(
    request_id: int,
    payload: InternalDecisionPayload,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    decision = payload.decision.strip().title()
    if decision not in {"Approved", "Rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be Approved or Rejected.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        actor = reviewer(conn, payload.actor_user_id)
        row = request_row(conn, request_id)
        if not row:
            raise HTTPException(status_code=404, detail="Request not found.")
        if row["status"] not in {"Pending", "Emergency Review"}:
            raise HTTPException(status_code=409, detail="This request is not ready for a decision.")
        reviewed_at = now_iso()
        applied_at = None
        if decision == "Approved" and payload.apply_change:
            updates: list[str] = []
            values: list[Any] = []
            for column, value in (
                ("shift_date", row.get("requested_date")),
                ("start_time", row.get("requested_start_time")),
                ("end_time", row.get("requested_end_time")),
            ):
                if value:
                    updates.append(f"{column}=?")
                    values.append(value)
            if updates:
                updates.extend(["status='Confirmed'", "updated_at=?"])
                values.extend([reviewed_at, row["shift_id"]])
                conn.execute(f"UPDATE scheduled_shifts SET {', '.join(updates)} WHERE id=?", tuple(values))
                applied_at = reviewed_at
        conn.execute(
            """
            UPDATE shift_change_requests
            SET status=?, reviewed_by_user_id=?, reviewed_at=?, decision_note=?, employee_notified=?, coverage_confirmed=?, applied_at=?
            WHERE id=?
            """,
            (decision, payload.actor_user_id, reviewed_at, payload.decision_note, int(payload.employee_notified), int(payload.coverage_confirmed), applied_at, request_id),
        )
        audit(conn, request_id, decision, payload.actor_user_id, None, payload.decision_note)
        conn.commit()
        return {"ok": True, "status": decision, "applied": bool(applied_at), "reviewed_by": actor.get("display_name")}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
