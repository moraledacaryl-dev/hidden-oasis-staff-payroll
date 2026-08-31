from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.security import current_user_from_token, require_api_key
from api.schedule_change_log import log_schedule_change
from api.upload_validation import MAX_UPLOAD_BYTES, validate_upload_bytes
from core.db import DB_PATH, fetchall, fetchone, get_conn, now_iso
from core.observability import business_today

router = APIRouter(prefix="/api/v1")
UPLOAD_DIR = Path(os.getenv("STAFF_UPLOAD_DIR", "data/staff_uploads"))


class ShiftChangeRequestPayload(BaseModel):
    shift_id: int
    request_type: str = Field(..., min_length=2, max_length=60)
    requested_date: date | None = None
    requested_start_time: str | None = None
    requested_end_time: str | None = None
    reason: str = Field(..., min_length=3, max_length=1000)
    proposed_swap_employee_id: int | None = None
    proposed_swap_shift_id: int | None = None
    emergency: bool = False
    accuracy_confirmed: bool = True


class ShiftChangeDecisionPayload(BaseModel):
    decision: str
    decision_note: str | None = None
    employee_notified: bool = False
    coverage_confirmed: bool = False
    apply_change: bool = True


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS shift_change_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_no TEXT UNIQUE,
            employee_id INTEGER NOT NULL,
            shift_id INTEGER NOT NULL,
            request_type TEXT NOT NULL,
            original_date TEXT NOT NULL,
            original_start_time TEXT NOT NULL,
            original_end_time TEXT NOT NULL,
            requested_date TEXT,
            requested_start_time TEXT,
            requested_end_time TEXT,
            reason TEXT NOT NULL,
            proposed_swap_employee_id INTEGER,
            swap_confirmed_at TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            emergency INTEGER NOT NULL DEFAULT 0,
            accuracy_confirmed INTEGER NOT NULL DEFAULT 1,
            employee_notified INTEGER NOT NULL DEFAULT 0,
            coverage_confirmed INTEGER NOT NULL DEFAULT 0,
            attachment_path TEXT,
            submitted_by_user_id INTEGER NOT NULL,
            submitted_at TEXT NOT NULL,
            reviewed_by_user_id INTEGER,
            reviewed_at TEXT,
            decision_note TEXT,
            withdrawn_at TEXT,
            applied_at TEXT
        );
        CREATE TABLE IF NOT EXISTS shift_change_request_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            actor_user_id INTEGER,
            actor_employee_id INTEGER,
            note TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_shift_change_requests_employee ON shift_change_requests(employee_id);
        CREATE INDEX IF NOT EXISTS idx_shift_change_requests_status ON shift_change_requests(status);
        CREATE INDEX IF NOT EXISTS idx_shift_change_requests_shift ON shift_change_requests(shift_id);
        """
    )
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(shift_change_requests)")}
    if "proposed_swap_shift_id" not in columns:
        conn.execute("ALTER TABLE shift_change_requests ADD COLUMN proposed_swap_shift_id INTEGER")
    conn.commit()


def employee_for_user(conn, user: dict[str, Any]) -> dict[str, Any]:
    account = fetchone(conn, "SELECT employee_id FROM app_users WHERE id=? AND active=1", (user.get("id"),))
    employee_id = int(account.get("employee_id") or 0) if account else 0
    if not employee_id:
        raise HTTPException(status_code=403, detail="Account is not linked to an employee record.")
    employee = fetchone(conn, "SELECT * FROM employees WHERE id=? AND COALESCE(status, 'Active') != 'Inactive'", (employee_id,))
    if not employee:
        raise HTTPException(status_code=403, detail="Linked employee record is inactive or missing.")
    return employee


def require_staff_user(x_api_key: str | None, user: dict[str, Any]) -> dict[str, Any]:
    require_api_key(x_api_key)
    if user.get("role_key") != "staff":
        raise HTTPException(status_code=403, detail="Staff self-service account required.")
    return user


def require_reviewer(x_api_key: str | None, user: dict[str, Any]) -> dict[str, Any]:
    require_api_key(x_api_key)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Owner, payroll, or General Manager access required.")
    return user


def audit(conn, request_id: int, action: str, user_id: int | None, employee_id: int | None = None, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO shift_change_request_audit(request_id, action, actor_user_id, actor_employee_id, note, created_at) VALUES(?,?,?,?,?,?)",
        (request_id, action, user_id, employee_id, note, now_iso()),
    )


def request_row(conn, request_id: int) -> dict[str, Any] | None:
    return fetchone(
        conn,
        """
        SELECT r.*, e.full_name AS employee_name, e.employee_code, e.department,
               se.full_name AS swap_employee_name,
               u.display_name AS reviewed_by_name
        FROM shift_change_requests r
        JOIN employees e ON e.id=r.employee_id
        LEFT JOIN employees se ON se.id=r.proposed_swap_employee_id
        LEFT JOIN app_users u ON u.id=r.reviewed_by_user_id
        WHERE r.id=?
        """,
        (request_id,),
    )


def schedule_items(conn, employee_id: int) -> list[dict[str, Any]]:
    today = business_today()
    start = (today - timedelta(days=7)).isoformat()
    end = (today + timedelta(days=35)).isoformat()
    return fetchall(
        conn,
        """
        SELECT id, employee_id, shift_date, start_time, end_time, position, department,
               break_minutes, status, notes, updated_at
        FROM scheduled_shifts
        WHERE employee_id=? AND date(shift_date) BETWEEN date(?) AND date(?)
          AND COALESCE(status, 'Draft') NOT IN ('Cancelled', 'Deleted')
        ORDER BY date(shift_date), start_time
        """,
        (employee_id, start, end),
    )


def shift_interval(shift: dict[str, Any]) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(
        f"{str(shift.get('shift_date') or '')[:10]}T{str(shift.get('start_time') or '')[:5]}"
    )
    end = datetime.fromisoformat(
        f"{str(shift.get('shift_date') or '')[:10]}T{str(shift.get('end_time') or '')[:5]}"
    )
    if end <= start:
        end += timedelta(days=1)
    return start, end


def conflicting_shift(
    conn,
    employee_id: int,
    proposed: dict[str, Any],
    exclude_ids: set[int],
) -> dict[str, Any] | None:
    start, end = shift_interval(proposed)
    rows = fetchall(
        conn,
        """
        SELECT * FROM scheduled_shifts
        WHERE employee_id=?
          AND date(shift_date) BETWEEN date(?, '-1 day') AND date(?, '+1 day')
          AND COALESCE(status,'Draft') NOT IN ('Cancelled','Deleted')
        """,
        (employee_id, start.date().isoformat(), end.date().isoformat()),
    )
    for row in rows:
        if int(row.get("id") or 0) in exclude_ids:
            continue
        other_start, other_end = shift_interval(row)
        if start < other_end and other_start < end:
            return row
    return None


def my_self_service(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = employee_for_user(conn, user)
        employee_id = int(employee["id"])
        requests = fetchall(
            conn,
            """
            SELECT r.*, se.full_name AS swap_employee_name
            FROM shift_change_requests r
            LEFT JOIN employees se ON se.id=r.proposed_swap_employee_id
            WHERE r.employee_id=? OR r.proposed_swap_employee_id=?
            ORDER BY r.submitted_at DESC, r.id DESC
            """,
            (employee_id, employee_id),
        )
        coworkers = fetchall(
            conn,
            "SELECT id, full_name, employee_code, department, position FROM employees WHERE id<>? AND COALESCE(status,'Active')!='Inactive' ORDER BY full_name",
            (employee_id,),
        )
        return {
            "ok": True,
            "employee": {
                "id": employee_id,
                "name": employee.get("full_name") or employee.get("name"),
                "employee_code": employee.get("employee_code"),
                "department": employee.get("department") or employee.get("department_name") or "Unassigned",
                "position": employee.get("position"),
            },
            "schedule": schedule_items(conn, employee_id),
            "requests": requests,
            "coworkers": coworkers,
        }
    finally:
        conn.close()


@router.post("/me/shift-change-requests")
def submit_shift_change_request(
    payload: ShiftChangeRequestPayload,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    if not payload.accuracy_confirmed:
        raise HTTPException(status_code=400, detail="Accuracy confirmation is required.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = employee_for_user(conn, user)
        employee_id = int(employee["id"])
        shift = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=? AND employee_id=?", (payload.shift_id, employee_id))
        if not shift:
            raise HTTPException(status_code=404, detail="The selected shift was not found in your schedule.")
        duplicate = fetchone(conn, "SELECT id FROM shift_change_requests WHERE shift_id=? AND employee_id=? AND status IN ('Pending','Swap Confirmation','Emergency Review')", (payload.shift_id, employee_id))
        if duplicate:
            raise HTTPException(status_code=409, detail="A pending request already exists for this shift.")
        request_type = payload.request_type.strip()
        is_swap = request_type.lower() in {"shift swap", "swap"}
        if is_swap and not payload.proposed_swap_employee_id:
            raise HTTPException(status_code=400, detail="Choose the employee proposed for the swap.")
        if is_swap and not payload.proposed_swap_shift_id:
            raise HTTPException(status_code=400, detail="Choose the shift proposed for the swap.")
        if payload.proposed_swap_employee_id == employee_id:
            raise HTTPException(status_code=400, detail="You cannot swap a shift with yourself.")
        if is_swap:
            counterpart = fetchone(
                conn,
                """
                SELECT * FROM scheduled_shifts
                WHERE id=? AND employee_id=?
                  AND COALESCE(status,'Draft') NOT IN ('Cancelled','Deleted')
                """,
                (payload.proposed_swap_shift_id, payload.proposed_swap_employee_id),
            )
            if not counterpart:
                raise HTTPException(status_code=404, detail="The proposed swap shift is no longer available.")
        initial_status = "Emergency Review" if payload.emergency else ("Swap Confirmation" if is_swap else "Pending")
        submitted_at = now_iso()
        cursor = conn.execute(
            """
            INSERT INTO shift_change_requests(
                employee_id, shift_id, request_type, original_date, original_start_time, original_end_time,
                requested_date, requested_start_time, requested_end_time, reason, proposed_swap_employee_id,
                proposed_swap_shift_id, status, emergency, accuracy_confirmed, submitted_by_user_id, submitted_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                employee_id, payload.shift_id, request_type, shift["shift_date"], shift["start_time"], shift["end_time"],
                payload.requested_date.isoformat() if payload.requested_date else None,
                payload.requested_start_time, payload.requested_end_time, payload.reason.strip(),
                payload.proposed_swap_employee_id, payload.proposed_swap_shift_id, initial_status,
                int(payload.emergency), 1, int(user["id"]), submitted_at,
            ),
        )
        request_id = int(cursor.lastrowid)
        request_no = f"SCR-{business_today():%Y%m%d}-{request_id:05d}"
        conn.execute("UPDATE shift_change_requests SET request_no=? WHERE id=?", (request_no, request_id))
        audit(conn, request_id, "Submitted", int(user["id"]), employee_id, payload.reason.strip())
        conn.commit()
        return {"ok": True, "request_id": request_id, "request_no": request_no, "status": initial_status}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/me/shift-change-requests/{request_id}/withdraw")
def withdraw_shift_change_request(
    request_id: int,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = employee_for_user(conn, user)
        row = fetchone(conn, "SELECT * FROM shift_change_requests WHERE id=? AND employee_id=?", (request_id, employee["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Request not found.")
        if row["status"] not in {"Pending", "Swap Confirmation", "Emergency Review"}:
            raise HTTPException(status_code=409, detail="Only pending requests can be withdrawn.")
        conn.execute("UPDATE shift_change_requests SET status='Withdrawn', withdrawn_at=? WHERE id=?", (now_iso(), request_id))
        audit(conn, request_id, "Withdrawn", int(user["id"]), int(employee["id"]))
        conn.commit()
        return {"ok": True, "status": "Withdrawn"}
    finally:
        conn.close()


@router.post("/me/shift-change-requests/{request_id}/confirm-swap")
def confirm_shift_swap(
    request_id: int,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = employee_for_user(conn, user)
        row = fetchone(conn, "SELECT * FROM shift_change_requests WHERE id=? AND proposed_swap_employee_id=?", (request_id, employee["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Swap request not found for your confirmation.")
        if row["status"] != "Swap Confirmation":
            raise HTTPException(status_code=409, detail="This swap is no longer awaiting confirmation.")
        confirmed_at = now_iso()
        conn.execute("UPDATE shift_change_requests SET status='Pending', swap_confirmed_at=? WHERE id=?", (confirmed_at, request_id))
        audit(conn, request_id, "Swap Confirmed", int(user["id"]), int(employee["id"]))
        conn.commit()
        return {"ok": True, "status": "Pending"}
    finally:
        conn.close()


@router.post("/me/shift-change-requests/{request_id}/decline-swap")
def decline_shift_swap(
    request_id: int,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = employee_for_user(conn, user)
        row = fetchone(conn, "SELECT * FROM shift_change_requests WHERE id=? AND proposed_swap_employee_id=?", (request_id, employee["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Swap request not found for your confirmation.")
        if row["status"] != "Swap Confirmation":
            raise HTTPException(status_code=409, detail="This swap is no longer awaiting confirmation.")
        declined_at = now_iso()
        conn.execute(
            "UPDATE shift_change_requests SET status='Swap Declined', decision_note=COALESCE(NULLIF(decision_note,''),'Swap declined by proposed swap employee.'), reviewed_at=COALESCE(reviewed_at, ?) WHERE id=?",
            (declined_at, request_id),
        )
        audit(conn, request_id, "Swap Declined", int(user["id"]), int(employee["id"]))
        conn.commit()
        return {"ok": True, "status": "Swap Declined"}
    finally:
        conn.close()


@router.post("/me/shift-change-requests/{request_id}/attachment")
def upload_shift_request_attachment(
    request_id: int,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    suffix = validate_upload_bytes(file.filename, raw)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = employee_for_user(conn, user)
        row = fetchone(conn, "SELECT * FROM shift_change_requests WHERE id=? AND employee_id=?", (request_id, employee["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Request not found.")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / f"shift-request-{request_id}-{now_iso().replace(':', '').replace(' ', '-')}{suffix}"
        target.write_bytes(raw)
        target.chmod(0o600)
        conn.execute("UPDATE shift_change_requests SET attachment_path=? WHERE id=?", (str(target), request_id))
        audit(conn, request_id, "Attachment Uploaded", int(user["id"]), int(employee["id"]), file.filename)
        conn.commit()
        return {"ok": True, "filename": file.filename}
    finally:
        conn.close()


@router.get("/schedule/change-requests")
def list_shift_change_requests(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_reviewer(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
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
def decide_shift_change_request(
    request_id: int,
    payload: ShiftChangeDecisionPayload,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_reviewer(x_api_key, user)
    decision = payload.decision.strip().title()
    if decision not in {"Approved", "Rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be Approved or Rejected.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        row = request_row(conn, request_id)
        if not row:
            raise HTTPException(status_code=404, detail="Request not found.")
        if row["status"] not in {"Pending", "Emergency Review"}:
            raise HTTPException(status_code=409, detail="This request is not ready for a decision.")
        reviewed_at = now_iso()
        applied_at = None
        if decision == "Approved" and payload.apply_change:
            is_swap = str(row.get("request_type") or "").strip().lower() in {"shift swap", "swap"}
            if is_swap:
                original = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (row["shift_id"],))
                counterpart = fetchone(
                    conn,
                    "SELECT * FROM scheduled_shifts WHERE id=?",
                    (row.get("proposed_swap_shift_id"),),
                )
                if (
                    not original
                    or not counterpart
                    or int(original.get("employee_id") or 0) != int(row["employee_id"])
                    or int(counterpart.get("employee_id") or 0) != int(row.get("proposed_swap_employee_id") or 0)
                ):
                    raise HTTPException(status_code=409, detail="One of the swap shifts changed. Review the request again.")
                excluded = {int(original["id"]), int(counterpart["id"])}
                if conflicting_shift(
                    conn,
                    int(counterpart["employee_id"]),
                    original,
                    excluded,
                ) or conflicting_shift(
                    conn,
                    int(original["employee_id"]),
                    counterpart,
                    excluded,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="The swap would overlap another scheduled shift.",
                    )
                conn.execute(
                    "UPDATE scheduled_shifts SET employee_id=?, status='Confirmed', updated_at=? WHERE id=?",
                    (counterpart["employee_id"], reviewed_at, original["id"]),
                )
                conn.execute(
                    "UPDATE scheduled_shifts SET employee_id=?, status='Confirmed', updated_at=? WHERE id=?",
                    (original["employee_id"], reviewed_at, counterpart["id"]),
                )
                for before, after_employee in (
                    (original, counterpart["employee_id"]),
                    (counterpart, original["employee_id"]),
                ):
                    log_schedule_change(
                        conn,
                        change_type="Shift swap approved",
                        entity_type="scheduled_shifts",
                        entity_id=int(before["id"]),
                        employee_id=int(after_employee),
                        work_date=str(before.get("shift_date") or ""),
                        before=before,
                        after={**before, "employee_id": after_employee},
                        changed_by=user.get("display_name"),
                        reason_category="Staff request",
                        reason_note=payload.decision_note or row.get("reason"),
                        attachment_ref=row.get("attachment_path"),
                    )
                applied_at = reviewed_at
            else:
                updates = []
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
                    before = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (row["shift_id"],))
                    if not before:
                        raise HTTPException(status_code=409, detail="The scheduled shift no longer exists.")
                    proposed = {
                        **before,
                        "shift_date": row.get("requested_date") or before.get("shift_date"),
                        "start_time": row.get("requested_start_time") or before.get("start_time"),
                        "end_time": row.get("requested_end_time") or before.get("end_time"),
                    }
                    if conflicting_shift(
                        conn,
                        int(row["employee_id"]),
                        proposed,
                        {int(row["shift_id"])},
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="The requested time overlaps another scheduled shift.",
                        )
                    updates.extend(["status='Confirmed'", "updated_at=?"])
                    values.extend([reviewed_at, row["shift_id"]])
                    conn.execute(f"UPDATE scheduled_shifts SET {', '.join(updates)} WHERE id=?", tuple(values))
                    after = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (row["shift_id"],))
                    log_schedule_change(
                        conn,
                        change_type="Staff shift request approved",
                        entity_type="scheduled_shifts",
                        entity_id=int(row["shift_id"]),
                        employee_id=int(row["employee_id"]),
                        work_date=str((after or row).get("shift_date") or ""),
                        before=before,
                        after=after,
                        changed_by=user.get("display_name"),
                        reason_category="Staff request",
                        reason_note=payload.decision_note or row.get("reason"),
                        attachment_ref=row.get("attachment_path"),
                    )
                    applied_at = reviewed_at
        conn.execute(
            """
            UPDATE shift_change_requests
            SET status=?, reviewed_by_user_id=?, reviewed_at=?, decision_note=?, employee_notified=?, coverage_confirmed=?, applied_at=?
            WHERE id=?
            """,
            (decision, int(user["id"]), reviewed_at, payload.decision_note, int(payload.employee_notified), int(payload.coverage_confirmed), applied_at, request_id),
        )
        audit(conn, request_id, decision, int(user["id"]), None, payload.decision_note)
        conn.commit()
        return {"ok": True, "status": decision, "applied": bool(applied_at)}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/schedule/change-requests/{request_id}")
def get_shift_change_request(
    request_id: int,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_reviewer(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        row = request_row(conn, request_id)
        if not row:
            raise HTTPException(status_code=404, detail="Request not found.")
        history = fetchall(conn, "SELECT * FROM shift_change_request_audit WHERE request_id=? ORDER BY created_at, id", (request_id,))
        return {"ok": True, "item": row, "history": history}
    finally:
        conn.close()
