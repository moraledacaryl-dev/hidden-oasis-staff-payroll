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
STAFF_HIDDEN_STATUSES = {"Draft", "Voided"}


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
    effective_start: date | None = None
    effective_end: date | None = None


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


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _add_column_if_missing(conn, table_name: str, column_name: str, ddl: str) -> None:
    if column_name in _columns(conn, table_name):
        return
    try:
        conn.execute(ddl)
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _employee_profile_sql(conn, *, name_alias: str = "full_name") -> tuple[str, str]:
    """Return schema-safe employee select expressions and optional joins."""
    employee_columns = _columns(conn, "employees")
    if "department" in employee_columns:
        department_expr = "e.department"
        department_join = ""
    elif "department_id" in employee_columns and _table_exists(conn, "departments"):
        department_expr = "d.name"
        department_join = "LEFT JOIN departments d ON d.id=e.department_id"
    else:
        department_expr = "NULL"
        department_join = ""
    position_expr = "e.position" if "position" in employee_columns else "NULL"
    return f"e.full_name AS {name_alias}, e.employee_code, {department_expr} AS department, {position_expr} AS position", department_join


def _employee_list_sql(conn, where_clause: str = "") -> str:
    profile_expr, department_join = _employee_profile_sql(conn, name_alias="full_name")
    return (
        f"SELECT e.id, {profile_expr} "
        "FROM employees e "
        f"{department_join} "
        f"{where_clause} "
        "ORDER BY e.full_name"
    )


def _date_text(value: date | str | None, fallback: str | None = None) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    return text[:10] if text else fallback


def entitlement_start(entitlement: dict[str, Any], year: int) -> str:
    return _date_text(entitlement.get("effective_start"), f"{year}-01-01") or f"{year}-01-01"


def entitlement_end(entitlement: dict[str, Any], year: int) -> str:
    return _date_text(entitlement.get("effective_end"), f"{year}-12-31") or f"{year}-12-31"


def ensure_schema(conn) -> None:
    conn.execute("""
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
    """)
    for column, definition in {
        "default_credits": "REAL NOT NULL DEFAULT 0",
        "paid": "INTEGER NOT NULL DEFAULT 1",
        "statutory": "INTEGER NOT NULL DEFAULT 0",
        "requires_approval": "INTEGER NOT NULL DEFAULT 1",
        "active": "INTEGER NOT NULL DEFAULT 1",
        "notes": "TEXT",
    }.items():
        _add_column_if_missing(conn, "leave_types", column, f"ALTER TABLE leave_types ADD COLUMN {column} {definition}")
    for name, credits, paid, statutory in (("SIL", 5, 1, 1), ("Sick Leave", 0, 1, 0), ("Bereavement Leave", 0, 1, 0), ("Unpaid Leave", 0, 0, 0)):
        conn.execute(
            "INSERT OR IGNORE INTO leave_types(name, default_credits, paid, statutory, active) VALUES(?,?,?,?,1)",
            (name, credits, paid, statutory),
        )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS employee_leave_entitlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_type_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            credits REAL NOT NULL DEFAULT 0,
            used REAL NOT NULL DEFAULT 0,
            entitled INTEGER NOT NULL DEFAULT 1,
            effective_start TEXT,
            effective_end TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id, leave_type_id, year)
        )
    """)
    for column, definition in {
        "credits": "REAL NOT NULL DEFAULT 0",
        "used": "REAL NOT NULL DEFAULT 0",
        "entitled": "INTEGER NOT NULL DEFAULT 1",
        "effective_start": "TEXT",
        "effective_end": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }.items():
        _add_column_if_missing(conn, "employee_leave_entitlements", column, f"ALTER TABLE employee_leave_entitlements ADD COLUMN {column} {definition}")

    conn.execute("""
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
    """)
    for column, definition in {
        "leave_type_id": "INTEGER",
        "start_date": "TEXT",
        "end_date": "TEXT",
        "days": "REAL NOT NULL DEFAULT 1",
        "paid": "INTEGER NOT NULL DEFAULT 1",
        "status": "TEXT NOT NULL DEFAULT 'Approved'",
        "reason": "TEXT",
        "reviewed_by": "TEXT",
        "reviewed_at": "TEXT",
        "created_at": "TEXT",
        "decision_note": "TEXT",
    }.items():
        _add_column_if_missing(conn, "leave_requests", column, f"ALTER TABLE leave_requests ADD COLUMN {column} {definition}")

    conn.execute("""
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
    """)
    for column, definition in {
        "record_type": "TEXT NOT NULL DEFAULT 'Memo'",
        "record_date": "TEXT",
        "subject": "TEXT NOT NULL DEFAULT ''",
        "details": "TEXT",
        "severity": "TEXT NOT NULL DEFAULT 'Info'",
        "status": "TEXT NOT NULL DEFAULT 'Issued'",
        "issued_by": "TEXT",
        "issued_role": "TEXT",
        "review_period_start": "TEXT",
        "review_period_end": "TEXT",
        "rating": "REAL",
        "acknowledged_at": "TEXT",
        "resolved_at": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }.items():
        _add_column_if_missing(conn, "hr_records", column, f"ALTER TABLE hr_records ADD COLUMN {column} {definition}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hr_records_employee ON hr_records(employee_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hr_records_type ON hr_records(record_type)")
    conn.commit()


def leave_request_used_days(conn, employee_id: int, leave_type_id: int, start_date: str, end_date: str) -> float:
    row = fetchone(conn, """
        SELECT COALESCE(SUM(days), 0) AS used
        FROM leave_requests
        WHERE employee_id=? AND leave_type_id=?
          AND date(start_date) <= date(?)
          AND date(end_date) >= date(?)
          AND status IN ('Approved', 'Paid', 'Used')
    """, (employee_id, leave_type_id, end_date, start_date))
    return float(row.get("used") or 0) if row else 0.0


def sync_entitlement_usage(conn, employee_id: int, leave_type_id: int, year: int, effective_start: str | None = None, effective_end: str | None = None) -> float:
    start = effective_start or f"{year}-01-01"
    end = effective_end or f"{year}-12-31"
    used = leave_request_used_days(conn, employee_id, leave_type_id, start, end)
    conn.execute(
        "UPDATE employee_leave_entitlements SET used=?, updated_at=CURRENT_TIMESTAMP WHERE employee_id=? AND leave_type_id=? AND year=?",
        (used, employee_id, leave_type_id, year),
    )
    return used


@router.get("/hr/leave-balances")
def leave_balances(year: int = Query(default_factory=lambda: date.today().year), authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_hr_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if user.get("role_key") == "staff":
            employees = fetchall(conn, _employee_list_sql(conn, "WHERE e.id=?"), (int(user["employee_id"]),))
        else:
            employees = fetchall(conn, _employee_list_sql(conn))
        types = fetchall(conn, "SELECT id, name, default_credits, paid, active FROM leave_types WHERE active=1 ORDER BY name")
        entitlements = fetchall(conn, """
            SELECT ele.*, lt.name AS leave_type_name, lt.paid
            FROM employee_leave_entitlements ele
            JOIN leave_types lt ON lt.id=ele.leave_type_id
            WHERE ele.year=?
            ORDER BY ele.employee_id, lt.name
        """, (year,))
        allowed_ids = {int(emp["id"]) for emp in employees}
        by_employee: dict[int, list[dict[str, Any]]] = {}
        for ent in entitlements:
            employee_id = int(ent["employee_id"])
            if employee_id not in allowed_ids:
                continue
            start = entitlement_start(ent, year)
            end = entitlement_end(ent, year)
            used = sync_entitlement_usage(conn, employee_id, int(ent["leave_type_id"]), year, start, end)
            credits = float(ent.get("credits") or 0)
            by_employee.setdefault(employee_id, []).append({
                "leave_type_id": ent["leave_type_id"],
                "leave_type_name": ent["leave_type_name"],
                "credits": credits,
                "used": used,
                "remaining": max(0.0, credits - used),
                "entitled": int(ent.get("entitled") or 0),
                "paid": int(ent.get("paid") or 0),
                "effective_start": start,
                "effective_end": end,
            })
        conn.commit()
        return {"ok": True, "year": year, "leave_types": types, "items": [{**dict(emp), "balances": by_employee.get(int(emp["id"]), [])} for emp in employees]}
    finally:
        conn.close()


@router.post("/hr/leave-entitlements")
def save_leave_entitlement(payload: LeaveEntitlementPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_payroll_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        if not fetchone(conn, "SELECT id FROM leave_types WHERE id=?", (payload.leave_type_id,)):
            raise HTTPException(status_code=404, detail="Leave type not found.")
        start = _date_text(payload.effective_start, f"{payload.year}-01-01")
        end = _date_text(payload.effective_end, f"{payload.year}-12-31")
        if start and end and start > end:
            raise HTTPException(status_code=422, detail="Effective end cannot be before effective start.")
        stamp = now_sql(conn)
        used = leave_request_used_days(conn, payload.employee_id, payload.leave_type_id, start or f"{payload.year}-01-01", end or f"{payload.year}-12-31")
        conn.execute("""
            INSERT INTO employee_leave_entitlements(employee_id, leave_type_id, year, credits, used, entitled, effective_start, effective_end, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, leave_type_id, year)
            DO UPDATE SET credits=excluded.credits, used=excluded.used, entitled=excluded.entitled, effective_start=excluded.effective_start, effective_end=excluded.effective_end, updated_at=excluded.updated_at
        """, (payload.employee_id, payload.leave_type_id, payload.year, payload.credits, used, int(payload.entitled or 0), start, end, stamp, stamp))
        log_audit(conn, actor=user.get("display_name"), action="Leave entitlement saved", table_name="employee_leave_entitlements", details={"employee_id": payload.employee_id, "leave_type_id": payload.leave_type_id, "year": payload.year, "credits": payload.credits, "used": used, "entitled": int(payload.entitled or 0), "effective_start": start, "effective_end": end})
        conn.commit()
        return {"ok": True, "message": "Leave entitlement saved.", "used": used}
    finally:
        conn.close()


@router.get("/hr/leave-requests")
def list_leave_requests(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_hr_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        profile_expr, department_join = _employee_profile_sql(conn, name_alias="employee_name")
        items = fetchall(conn, f"""
            SELECT lr.*, {profile_expr}, lt.name AS leave_type_name
            FROM leave_requests lr
            JOIN employees e ON e.id=lr.employee_id
            {department_join}
            LEFT JOIN leave_types lt ON lt.id=lr.leave_type_id
            ORDER BY CASE lr.status WHEN 'Pending' THEN 0 ELSE 1 END, date(lr.start_date) DESC, lr.id DESC
        """)
        return {"ok": True, "items": items}
    finally:
        conn.close()


@router.post("/hr/leave-requests/{request_id}/decision")
def decide_leave_request(request_id: int, payload: LeaveDecisionPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
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
        conn.execute("UPDATE leave_requests SET status=?, reviewed_by=?, reviewed_at=?, decision_note=? WHERE id=?", (decision, user.get("display_name"), now_sql(conn), payload.decision_note, request_id))
        if row.get("leave_type_id"):
            year = int(str(row["start_date"])[:4])
            entitlements = fetchall(conn, "SELECT * FROM employee_leave_entitlements WHERE employee_id=? AND leave_type_id=? AND year=?", (int(row["employee_id"]), int(row["leave_type_id"]), year))
            for entitlement in entitlements:
                sync_entitlement_usage(conn, int(row["employee_id"]), int(row["leave_type_id"]), year, entitlement_start(entitlement, year), entitlement_end(entitlement, year))
        log_audit(conn, actor=user.get("display_name"), action=f"Leave request {decision.lower()}", table_name="leave_requests", record_id=request_id, details={"decision_note": payload.decision_note})
        conn.commit()
        return {"ok": True, "message": f"Leave request {decision.lower()}."}
    finally:
        conn.close()


@router.get("/hr/records")
def hr_records(employee_id: int | None = Query(default=None), record_type: str | None = Query(default=None), authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_hr_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        filters: list[str] = []
        params: list[Any] = []
        if user.get("role_key") == "staff":
            filters.append("hr.employee_id=?")
            params.append(int(user["employee_id"]))
            filters.append("hr.status NOT IN ('Draft','Voided')")
        elif employee_id:
            filters.append("hr.employee_id=?")
            params.append(employee_id)
        if record_type and record_type != "All":
            filters.append("hr.record_type=?")
            params.append(record_type)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        profile_expr, department_join = _employee_profile_sql(conn, name_alias="employee_name")
        items = fetchall(conn, f"""
            SELECT hr.*, {profile_expr}
            FROM hr_records hr
            JOIN employees e ON e.id=hr.employee_id
            {department_join}
            {where}
            ORDER BY date(hr.record_date) DESC, hr.id DESC
            LIMIT 500
        """, tuple(params))
        return {"ok": True, "items": items, "record_types": sorted(HR_TYPES), "types": sorted(HR_TYPES), "severities": sorted(SEVERITIES), "statuses": sorted(STATUSES)}
    finally:
        conn.close()


@router.post("/hr/records")
def create_hr_record(payload: HrRecordPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
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
        cur = conn.execute("""
            INSERT INTO hr_records(employee_id,record_type,record_date,subject,details,severity,status,issued_by,issued_role,review_period_start,review_period_end,rating,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (payload.employee_id, payload.record_type, payload.record_date.isoformat(), payload.subject.strip(), payload.details, payload.severity, payload.status, user.get("display_name"), user.get("role_key"), payload.review_period_start.isoformat() if payload.review_period_start else None, payload.review_period_end.isoformat() if payload.review_period_end else None, payload.rating, stamp, stamp))
        record_id = int(cur.lastrowid)
        log_audit(conn, actor=user.get("display_name"), action="HR record created", table_name="hr_records", record_id=record_id, details={"employee_id": payload.employee_id, "record_type": payload.record_type, "status": payload.status})
        conn.commit()
        return {"ok": True, "id": record_id, "message": "HR record saved."}
    finally:
        conn.close()
