from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from core.audit import log_audit
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

HR_TYPES = {"Annual Review", "Infraction", "Memo"}
SEVERITIES = {"Info", "Low", "Medium", "High", "Final"}
STATUSES = {"Draft", "Issued", "Acknowledged", "Resolved", "Voided"}


class HrRecordPayload(BaseModel):
    employee_id: int
    record_type: str
    record_date: date
    subject: str
    details: str | None = None
    severity: str = "Info"
    status: str = "Issued"
    review_period_start: date | None = None
    review_period_end: date | None = None
    rating: float | None = None


class LeaveEntitlementPayload(BaseModel):
    employee_id: int
    leave_type_id: int
    year: int
    credits: float
    entitled: int = 1


class LeaveDecisionPayload(BaseModel):
    status: str
    decision_note: str | None = None


def now_sql(conn) -> str:
    return str(conn.execute("SELECT datetime('now','localtime')").fetchone()[0])


def require_hr_viewer(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor", "staff"}:
        raise HTTPException(status_code=403, detail="HR access denied.")
    if user.get("role_key") == "staff" and not user.get("employee_id"):
        raise HTTPException(status_code=403, detail="Staff account is not linked to an employee record.")
    return user


def require_hr_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Only owner, payroll, or the General Manager can create HR records.")
    return user


def require_payroll_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Only owner or payroll can edit leave entitlements.")
    return user


def _add_column_if_missing(conn, table_name: str, column_name: str, ddl: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name in columns:
        return
    try:
        conn.execute(ddl)
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_credits REAL NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 1,
            statutory INTEGER NOT NULL DEFAULT 0,
            requires_approval INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_leave_entitlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_type_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            credits REAL NOT NULL DEFAULT 0,
            used REAL NOT NULL DEFAULT 0,
            entitled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id, leave_type_id, year)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_type_id INTEGER,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            days REAL NOT NULL DEFAULT 1,
            paid INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Approved',
            reason TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            record_type TEXT NOT NULL,
            record_date TEXT NOT NULL,
            subject TEXT NOT NULL,
            details TEXT,
            severity TEXT NOT NULL DEFAULT 'Info',
            status TEXT NOT NULL DEFAULT 'Issued',
            issued_by TEXT,
            issued_role TEXT,
            review_period_start TEXT,
            review_period_end TEXT,
            rating REAL,
            acknowledged_at TEXT,
            resolved_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hr_records_employee ON hr_records(employee_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hr_records_type ON hr_records(record_type)")
    _add_column_if_missing(conn, "leave_requests", "decision_note", "ALTER TABLE leave_requests ADD COLUMN decision_note TEXT")
    conn.commit()


def leave_request_used_days(conn, employee_id: int, leave_type_id: int, year: int) -> float:
    row = fetchone(
        conn,
        """
        SELECT COALESCE(SUM(days), 0) AS used
        FROM leave_requests
        WHERE employee_id=?
          AND leave_type_id=?
          AND strftime('%Y', start_date)=?
          AND status IN ('Approved', 'Paid', 'Used')
        """,
        (employee_id, leave_type_id, str(year)),
    )
    return float(row.get("used") or 0) if row else 0.0


def sync_entitlement_usage(conn, employee_id: int, leave_type_id: int, year: int) -> float:
    used = leave_request_used_days(conn, employee_id, leave_type_id, year)
    conn.execute(
        "UPDATE employee_leave_entitlements SET used=?, updated_at=CURRENT_TIMESTAMP WHERE employee_id=? AND leave_type_id=? AND year=?",
        (used, employee_id, leave_type_id, year),
    )
    return used


@router.get("/hr/leave-balances")
def leave_balances(
    year: int = Query(default_factory=lambda: date.today().year),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_hr_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if user.get("role_key") == "staff":
            employees = fetchall(
                conn,
                "SELECT id, full_name, employee_code, department, position FROM employees WHERE id=? ORDER BY full_name",
                (int(user["employee_id"]),),
            )
        else:
            employees = fetchall(conn, "SELECT id, full_name, employee_code, department, position FROM employees ORDER BY full_name")
        types = fetchall(conn, "SELECT id, name, default_credits, paid, active FROM leave_types WHERE active=1 ORDER BY name")
        entitlements = fetchall(
            conn,
            """
            SELECT ele.*, lt.name AS leave_type_name, lt.paid
            FROM employee_leave_entitlements ele
            JOIN leave_types lt ON lt.id=ele.leave_type_id
            WHERE ele.year=?
            ORDER BY ele.employee_id, lt.name
            """,
            (year,),
        )
        allowed_ids = {int(emp["id"]) for emp in employees}
        by_employee: dict[int, list[dict[str, Any]]] = {}
        for ent in entitlements:
            employee_id = int(ent["employee_id"])
            if employee_id not in allowed_ids:
                continue
            used = sync_entitlement_usage(conn, employee_id, int(ent["leave_type_id"]), year)
            credits = float(ent.get("credits") or 0)
            by_employee.setdefault(employee_id, []).append(
                {
                    "leave_type_id": ent["leave_type_id"],
                    "leave_type_name": ent["leave_type_name"],
                    "credits": credits,
                    "used": used,
                    "remaining": max(0.0, credits - used),
                    "entitled": int(ent.get("entitled") or 0),
                    "paid": int(ent.get("paid") or 0),
                }
            )
        conn.commit()
        return {
            "ok": True,
            "year": year,
            "leave_types": types,
            "items": [{**dict(emp), "balances": by_employee.get(int(emp["id"]), [])} for emp in employees],
        }
    finally:
        conn.close()


@router.post("/hr/leave-entitlements")
def save_leave_entitlement(
    payload: LeaveEntitlementPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_payroll_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        if not fetchone(conn, "SELECT id FROM leave_types WHERE id=?", (payload.leave_type_id,)):
            raise HTTPException(status_code=404, detail="Leave type not found.")
        conn.execute(
            """
            INSERT INTO employee_leave_entitlements(employee_id, leave_type_id, year, credits, entitled, used, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(employee_id, leave_type_id, year)
            DO UPDATE SET credits=excluded.credits, entitled=excluded.entitled, updated_at=excluded.updated_at
            """,
            (payload.employee_id, payload.leave_type_id, payload.year, payload.credits, int(payload.entitled or 0), now_sql(conn), now_sql(conn)),
        )
        sync_entitlement_usage(conn, payload.employee_id, payload.leave_type_id, payload.year)
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="Leave entitlement saved",
            table_name="employee_leave_entitlements",
            details={
                "employee_id": payload.employee_id,
                "leave_type_id": payload.leave_type_id,
                "year": payload.year,
                "credits": payload.credits,
                "entitled": int(payload.entitled or 0),
            },
        )
        conn.commit()
        return {"ok": True, "message": "Leave entitlement saved."}
    finally:
        conn.close()


@router.get("/hr/leave-requests")
def list_leave_requests(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_hr_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        items = fetchall(
            conn,
            """
            SELECT lr.*, e.full_name AS employee_name, e.employee_code, e.department,
                   lt.name AS leave_type_name
            FROM leave_requests lr
            JOIN employees e ON e.id=lr.employee_id
            LEFT JOIN leave_types lt ON lt.id=lr.leave_type_id
            ORDER BY CASE lr.status WHEN 'Pending' THEN 0 ELSE 1 END,
                     date(lr.start_date) DESC, lr.id DESC
            """,
        )
        return {"ok": True, "items": items}
    finally:
        conn.close()


@router.post("/hr/leave-requests/{request_id}/decision")
def decide_leave_request(
    request_id: int,
    payload: LeaveDecisionPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_hr_editor(authorization, x_api_key)
    decision = payload.status.strip().title()
    if decision not in {"Approved", "Rejected"}:
        raise HTTPException(status_code=422, detail="Decision must be Approved or Rejected.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        row = fetchone(conn, "SELECT * FROM leave_requests WHERE id=?", (request_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found.")
        if row.get("status") != "Pending":
            raise HTTPException(status_code=409, detail="This leave request has already been reviewed.")
        conn.execute(
            """
            UPDATE leave_requests
            SET status=?, reviewed_by=?, reviewed_at=?, decision_note=?
            WHERE id=?
            """,
            (decision, user.get("display_name"), now_sql(conn), payload.decision_note, request_id),
        )
        if row.get("leave_type_id"):
            sync_entitlement_usage(
                conn,
                int(row["employee_id"]),
                int(row["leave_type_id"]),
                int(str(row["start_date"])[:4]),
            )
        log_audit(
            conn,
            actor=user.get("display_name"),
            action=f"Leave request {decision.lower()}",
            table_name="leave_requests",
            record_id=request_id,
            details={"decision_note": payload.decision_note},
        )
        conn.commit()
        return {"ok": True, "message": f"Leave request {decision.lower()}."}
    finally:
        conn.close()


@router.get("/hr/records")
def hr_records(
    employee_id: int | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_hr_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if user.get("role_key") == "staff":
            employee_id = int(user["employee_id"])
        params: list[Any] = []
        where = "1=1"
        if employee_id:
            where += " AND hr.employee_id=?"
            params.append(employee_id)
        items = fetchall(
            conn,
            f"""
            SELECT hr.*, e.full_name AS employee_name, e.employee_code, e.department
            FROM hr_records hr
            JOIN employees e ON e.id=hr.employee_id
            WHERE {where}
            ORDER BY date(hr.record_date) DESC, hr.id DESC
            """,
            tuple(params),
        )
        return {"ok": True, "items": items, "types": sorted(HR_TYPES), "severities": sorted(SEVERITIES), "statuses": sorted(STATUSES)}
    finally:
        conn.close()


@router.post("/hr/records")
def create_hr_record(
    payload: HrRecordPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_hr_editor(authorization, x_api_key)
    if payload.record_type not in HR_TYPES:
        raise HTTPException(status_code=422, detail="Invalid HR record type.")
    if payload.severity not in SEVERITIES:
        raise HTTPException(status_code=422, detail="Invalid severity.")
    if payload.status not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        stamp = now_sql(conn)
        cur = conn.execute(
            """
            INSERT INTO hr_records(employee_id,record_type,record_date,subject,details,severity,status,issued_by,issued_role,review_period_start,review_period_end,rating,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload.employee_id,
                payload.record_type,
                payload.record_date.isoformat(),
                payload.subject.strip(),
                payload.details,
                payload.severity,
                payload.status,
                user.get("display_name"),
                user.get("role_key"),
                payload.review_period_start.isoformat() if payload.review_period_start else None,
                payload.review_period_end.isoformat() if payload.review_period_end else None,
                payload.rating,
                stamp,
                stamp,
            ),
        )
        log_audit(conn, actor=user.get("display_name"), action="HR record created", table_name="hr_records", record_id=int(cur.lastrowid), details={"employee_id": payload.employee_id, "type": payload.record_type})
        conn.commit()
        return {"ok": True, "id": int(cur.lastrowid), "message": "HR record saved."}
    finally:
        conn.close()
