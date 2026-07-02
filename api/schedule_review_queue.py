from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from api.schedule_standards import ensure_schedule_review_columns, now_iso, table_exists
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class ReviewDecisionPayload(BaseModel):
    decision: str = "Approved"
    decision_note: str | None = None


def require_reviewer(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Review queue requires owner, payroll, or General Manager access.")
    return user


def normalize_note(value: Any) -> str:
    return str(value or "").strip()


def schedule_items(conn) -> list[dict[str, Any]]:
    ensure_schedule_review_columns(conn)
    rows = fetchall(
        conn,
        """
        SELECT
            ss.id,
            ss.employee_id,
            ss.shift_date,
            ss.start_time,
            ss.end_time,
            ss.position,
            ss.department,
            ss.status,
            ss.review_status,
            ss.review_reason,
            ss.notes,
            e.full_name AS employee_name,
            e.employee_code
        FROM scheduled_shifts ss
        LEFT JOIN employees e ON e.id=ss.employee_id
        WHERE COALESCE(ss.status,'')='Needs Review'
           OR COALESCE(ss.review_status,'')='Needs Review'
        ORDER BY date(ss.shift_date), ss.start_time, COALESCE(e.full_name,'Unassigned')
        """,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("employee_name") or "Unassigned"
        items.append({
            "source_type": "schedule",
            "id": row["id"],
            "title": name,
            "subtitle": f"{row.get('shift_date')} · {row.get('start_time')}–{row.get('end_time')}",
            "date": row.get("shift_date"),
            "status": row.get("status") or row.get("review_status") or "Needs Review",
            "issue_summary": row.get("review_reason") or "Schedule needs review.",
            "detail": f"{row.get('position') or 'Shift'} · {row.get('department') or 'Unassigned'}",
            "priority": 1,
        })
    return items


def attendance_items(conn) -> list[dict[str, Any]]:
    if not table_exists(conn, "time_logs"):
        return []
    rows = fetchall(
        conn,
        """
        SELECT
            tl.id,
            tl.employee_id,
            tl.work_date,
            tl.actual_in,
            tl.actual_out,
            tl.attendance_status,
            tl.notes,
            tl.source,
            tl.approved_ot_hours,
            tl.is_absent,
            tl.absence_type,
            lt.name AS leave_type_name,
            lr.status AS leave_status,
            lr.reason AS leave_reason,
            e.full_name AS employee_name,
            e.employee_code,
            e.department
        FROM time_logs tl
        LEFT JOIN employees e ON e.id=tl.employee_id
        LEFT JOIN leave_requests lr
          ON lr.employee_id = tl.employee_id
         AND date(tl.work_date) BETWEEN date(lr.start_date) AND date(lr.end_date)
         AND COALESCE(lr.status,'') NOT IN ('Cancelled','Rejected','Withdrawn','Void','Voided')
        LEFT JOIN leave_types lt ON lt.id = lr.leave_type_id
        WHERE COALESCE(tl.attendance_status,'')='Needs Review'
        ORDER BY date(tl.work_date), COALESCE(e.full_name,'Unassigned'), tl.id
        """,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("employee_name") or "Unassigned"
        notes = normalize_note(row.get("notes"))
        absence_type = normalize_note(row.get("absence_type"))
        leave_type = normalize_note(row.get("leave_type_name"))
        leave_reason = normalize_note(row.get("leave_reason"))
        actual_in = normalize_note(row.get("actual_in"))
        actual_out = normalize_note(row.get("actual_out"))

        saved_leave_type = absence_type or leave_type

        if row.get("is_absent") or saved_leave_type:
            current_state = saved_leave_type or "Absent"
        elif actual_in or actual_out:
            current_state = f"Time log {actual_in or '—'}–{actual_out or '—'}"
        else:
            current_state = "Missing time log"

        issue = notes or leave_reason or "Attendance item needs review."
        items.append({
            "source_type": "attendance",
            "id": row["id"],
            "title": name,
            "subtitle": f"{row.get('work_date')} · {current_state}",
            "date": row.get("work_date"),
            "status": row.get("attendance_status") or "Needs Review",
            "issue_summary": current_state,
            "detail": issue,
            "priority": 2,
        })
    return items


def shift_request_items(conn) -> list[dict[str, Any]]:
    if not table_exists(conn, "shift_change_requests"):
        return []
    rows = fetchall(
        conn,
        """
        SELECT
            r.*,
            e.full_name AS employee_name,
            e.employee_code,
            e.department,
            se.full_name AS swap_employee_name
        FROM shift_change_requests r
        JOIN employees e ON e.id=r.employee_id
        LEFT JOIN employees se ON se.id=r.proposed_swap_employee_id
        WHERE r.status IN ('Pending','Emergency Review','Swap Confirmation')
        ORDER BY CASE r.status WHEN 'Emergency Review' THEN 0 WHEN 'Pending' THEN 1 WHEN 'Swap Confirmation' THEN 2 ELSE 3 END,
                 r.submitted_at DESC,
                 r.id DESC
        """,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        requested_date = row.get("requested_date") or row.get("original_date")
        requested_start = row.get("requested_start_time") or row.get("original_start_time")
        requested_end = row.get("requested_end_time") or row.get("original_end_time")
        reason = normalize_note(row.get("reason"))
        swap = f" · swap with {row.get('swap_employee_name')}" if row.get("swap_employee_name") else ""
        items.append({
            "source_type": "shift_request",
            "id": row["id"],
            "request_no": row.get("request_no"),
            "title": row.get("employee_name") or "Employee request",
            "subtitle": f"{requested_date} · {requested_start}–{requested_end}",
            "date": requested_date,
            "status": row.get("status"),
            "issue_summary": reason or "Shift-change request needs decision.",
            "detail": f"{row.get('request_type')}{swap}",
            "priority": 0 if row.get("status") == "Emergency Review" else 3,
        })
    return items


@router.get("/schedule/review-queue")
def review_queue(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_reviewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        items = schedule_items(conn) + attendance_items(conn) + shift_request_items(conn)
        items.sort(key=lambda item: (int(item.get("priority") or 9), str(item.get("date") or ""), str(item.get("title") or "")))
        return {
            "ok": True,
            "items": items,
            "summary": {
                "total": len(items),
                "schedule": sum(1 for item in items if item["source_type"] == "schedule"),
                "attendance": sum(1 for item in items if item["source_type"] == "attendance"),
                "shift_requests": sum(1 for item in items if item["source_type"] == "shift_request"),
            },
        }
    finally:
        conn.close()


@router.post("/schedule/review-queue/{source_type}/{item_id}/decision")
def decide_review_item(
    source_type: str,
    item_id: int,
    payload: ReviewDecisionPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_reviewer(authorization, x_api_key)
    decision = payload.decision.strip().title() or "Approved"
    if decision != "Approved":
        raise HTTPException(status_code=422, detail="Review queue only supports Approve. Fix issues by editing the schedule or attendance record first.")

    note = normalize_note(payload.decision_note)
    reviewer = user.get("display_name") or "Reviewer"
    stamp = now_iso()

    conn = get_conn(DB_PATH)
    try:
        if source_type == "schedule":
            ensure_schedule_review_columns(conn)
            row = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (item_id,))
            if not row:
                raise HTTPException(status_code=404, detail="Schedule row not found.")

            conn.execute(
                """
                UPDATE scheduled_shifts
                SET status='Approved',
                    review_status='Approved',
                    review_reason=?,
                    reviewed_by=?,
                    reviewed_at=?,
                    approved_exception=1,
                    updated_at=?
                WHERE id=?
                """,
                (note or row.get("review_reason"), reviewer, stamp, stamp, item_id),
            )
            conn.commit()
            return {"ok": True, "source_type": source_type, "id": item_id, "status": "Approved"}

        if source_type == "attendance":
            row = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (item_id,))
            if not row:
                raise HTTPException(status_code=404, detail="Attendance row not found.")

            existing_notes = normalize_note(row.get("notes"))
            review_note = "Review decision: Approved"
            if note:
                review_note += f" - {note}"
            notes = " | ".join(part for part in [existing_notes, review_note] if part)

            conn.execute(
                """
                UPDATE time_logs
                SET attendance_status='Approved',
                    reviewed_by=?,
                    reviewed_at=?,
                    notes=?,
                    updated_at=?
                WHERE id=?
                """,
                (reviewer, stamp, notes, stamp, item_id),
            )
            conn.commit()
            return {"ok": True, "source_type": source_type, "id": item_id, "status": "Approved"}

        raise HTTPException(status_code=422, detail="Use the shift request approval endpoint for staff requests.")
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
