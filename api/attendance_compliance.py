from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class AttendanceMemoPayload(BaseModel):
    employee_id: int
    period_month: str
    memo_type: str
    memo_level: str
    reason: str
    notes: str | None = None
    status: str = "Issued"


def require_attendance_compliance_user(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "supervisor"}:
        raise HTTPException(status_code=403, detail="Attendance compliance requires owner or General Manager access.")
    return user


def month_bounds(period_month: str) -> tuple[str, str]:
    try:
        start = datetime.strptime(period_month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="period month must be YYYY-MM.") from exc
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    end = next_month - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")



def minutes_late_from_times(start_time: str | None, actual_in: str | None) -> int | None:
    if not start_time or not actual_in:
        return None
    try:
        start_h, start_m = [int(part) for part in str(start_time)[:5].split(":")[:2]]
        in_h, in_m = [int(part) for part in str(actual_in)[:5].split(":")[:2]]
    except Exception:
        return None
    scheduled_minutes = start_h * 60 + start_m
    actual_minutes = in_h * 60 + in_m
    diff = actual_minutes - scheduled_minutes
    return diff if diff > 0 else 0


def classify_late_minutes(minutes_late: int | None) -> str:
    if minutes_late is None:
        return "Missing"
    if minutes_late <= 0:
        return "ON-TIME"
    if minutes_late <= 5:
        return "Grace Period"
    if minutes_late > 30:
        return "Partial Absence"
    return "LATE"


def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def first_existing(cols: set[str], names: list[str]) -> str | None:
    for name in names:
        if name in cols:
            return name
    return None


def sql_value_expr(cols: set[str], names: list[str], fallback: str, alias: str) -> str:
    col = first_existing(cols, names)
    return f"s.{quote_ident(col)} AS {alias}" if col else f"{fallback} AS {alias}"


def fetch_compliance_shifts(conn, period_start: str, period_end: str) -> list[dict[str, Any]]:
    """Return normalized schedule rows from the editable schedule table only.

    Legacy schedule rows must be migrated into scheduled_shifts before they can
    affect compliance/payroll behavior. This keeps imported data behaving the
    same as schedule rows created inside the app.
    """
    if not table_exists(conn, "scheduled_shifts"):
        return []
    return fetchall(
        conn,
        """
        SELECT id, employee_id, shift_date, start_time, end_time, 'scheduled_shifts' AS schedule_source
        FROM scheduled_shifts
        WHERE employee_id IS NOT NULL
          AND date(shift_date) BETWEEN date(?) AND date(?)
        ORDER BY shift_date, start_time
        """,
        (period_start, period_end),
    )


def ensure_column(conn, table: str, column: str, definition: str) -> None:
    if table_exists(conn, table) and column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            period_month TEXT NOT NULL,
            memo_type TEXT NOT NULL,
            memo_level TEXT NOT NULL,
            reason TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'Issued',
            issued_by TEXT,
            issued_at TEXT,
            acknowledged_by TEXT,
            acknowledged_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_memos_employee_month ON attendance_memos(employee_id, period_month)")
    if table_exists(conn, "time_logs"):
        ensure_column(conn, "time_logs", "notice_given_at", "TEXT")
        ensure_column(conn, "time_logs", "notice_timing", "TEXT")
        ensure_column(conn, "time_logs", "evidence_ref", "TEXT")
    conn.commit()


def parse_time(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    text = str(value)[:5]
    try:
        hour, minute = text.split(":")
        return int(hour), int(minute)
    except (ValueError, TypeError):
        return None


def late_minutes(shift_date: str, scheduled_start: str | None, actual_in: str | None) -> int:
    scheduled = parse_time(scheduled_start)
    actual = parse_time(actual_in)
    if not scheduled or not actual:
        return 0
    scheduled_dt = datetime.fromisoformat(f"{shift_date[:10]}T{scheduled[0]:02d}:{scheduled[1]:02d}:00")
    actual_dt = datetime.fromisoformat(f"{shift_date[:10]}T{actual[0]:02d}:{actual[1]:02d}:00")
    delta = int((actual_dt - scheduled_dt).total_seconds() // 60)
    return max(0, delta)


def handbook_action(lates: int, partial_absences: int, unexcused_absences: int, awol: int) -> str:
    actions: list[str] = []
    if lates >= 8:
        actions.append("Late: final written warning + 30-day improvement plan")
    elif lates >= 5:
        actions.append("Late: formal memo")
    elif lates >= 3:
        actions.append("Late: verbal warning")

    if partial_absences >= 4:
        actions.append("Partial absence: final review")
    elif partial_absences >= 3:
        actions.append("Partial absence: written notice + 30-day probation")
    elif partial_absences >= 2:
        actions.append("Partial absence: formal memo")
    elif partial_absences >= 1:
        actions.append("Partial absence: verbal warning")

    if unexcused_absences >= 4:
        actions.append("Unexcused absence: final review")
    elif unexcused_absences >= 3:
        actions.append("Unexcused absence: written notice + 30-day probation")
    elif unexcused_absences >= 2:
        actions.append("Unexcused absence: formal memo")
    elif unexcused_absences >= 1:
        actions.append("Unexcused absence: verbal warning")

    if awol >= 2:
        actions.append("AWOL: final review")
    elif awol >= 1:
        actions.append("AWOL: written notice + 30-day probation")

    return "; ".join(actions) if actions else "No action required"


def reward_status(year_unexcused: int) -> str:
    if year_unexcused == 0:
        return "Eligible: 2 additional paid leave days next year"
    if 1 <= year_unexcused <= 3:
        return "Eligible: 1 additional paid leave day next year"
    return "Not eligible for attendance-based reward"


@router.get("/attendance/compliance")
def attendance_compliance(
    month: str = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_attendance_compliance_user(authorization, x_api_key)
    start, end = month_bounds(month)
    year_start = date.fromisoformat(start).replace(month=1, day=1).isoformat()
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employees = fetchall(conn, "SELECT id, full_name, department, position, status FROM employees WHERE status != 'Inactive' ORDER BY full_name")
        shifts = fetch_compliance_shifts(conn, start, end)
        month_logs = fetchall(conn, "SELECT * FROM time_logs WHERE date(work_date) BETWEEN date(?) AND date(?)", (start, end))
        year_logs = fetchall(conn, "SELECT * FROM time_logs WHERE date(work_date) BETWEEN date(?) AND date(?)", (year_start, end))
        log_map = {(int(row["employee_id"]), str(row["work_date"])[:10]): row for row in month_logs if row.get("employee_id")}
        schedule_by_employee: dict[int, list[dict[str, Any]]] = {}
        for shift in shifts:
            schedule_by_employee.setdefault(int(shift["employee_id"]), []).append(shift)
        year_absences: dict[int, int] = {}
        for row in year_logs:
            if int(row.get("is_absent") or 0) and str(row.get("absence_type") or "").lower() in {"unexcused", "unexcused absence", "awol"}:
                year_absences[int(row["employee_id"])] = year_absences.get(int(row["employee_id"]), 0) + 1

        items: list[dict[str, Any]] = []
        for employee in employees:
            employee_id = int(employee["id"])
            employee_shifts = schedule_by_employee.get(employee_id, [])
            lates = 0
            grace = 0
            partial_absences = 0
            unexcused = 0
            awol = 0
            missing_logs = 0
            for shift in employee_shifts:
                shift_date = str(shift["shift_date"])[:10]
                log = log_map.get((employee_id, shift_date))
                if not log:
                    missing_logs += 1
                    continue
                absence_type = str(log.get("absence_type") or "").lower()
                if int(log.get("is_absent") or 0):
                    if "awol" in absence_type:
                        awol += 1
                    elif "unexcused" in absence_type:
                        unexcused += 1
                    continue
                minutes = late_minutes(shift_date, str(shift.get("start_time") or ""), str(log.get("actual_in") or ""))
                status = classify_late_minutes(minutes)
                if status == "Grace Period":
                    grace += 1
                elif status == "LATE":
                    lates += 1
                elif status == "Partial Absence":
                    partial_absences += 1
            action = handbook_action(lates, partial_absences, unexcused, awol)
            items.append({
                "employee_id": employee_id,
                "employee_name": employee["full_name"],
                "department": employee.get("department"),
                "position": employee.get("position"),
                "scheduled_days": len(employee_shifts),
                "missing_logs": missing_logs,
                "lates": lates,
                "grace_periods": grace,
                "partial_absences": partial_absences,
                "unexcused_absences": unexcused,
                "awol": awol,
                "recommended_action": action,
                "reward_status": reward_status(year_absences.get(employee_id, 0)),
            })
        return {"ok": True, "month": month, "checked_by": user.get("display_name"), "items": items, "mode": "attendance_compliance_scheduled_shifts_only"}
    finally:
        conn.close()


@router.post("/attendance/memos")
def create_attendance_memo(payload: AttendanceMemoPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_attendance_compliance_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO attendance_memos(employee_id, period_month, memo_type, memo_level, reason, notes, status, issued_by, issued_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload.employee_id, payload.period_month, payload.memo_type, payload.memo_level, payload.reason, payload.notes, payload.status, user.get("display_name"), now_iso()),
        )
        conn.commit()
        return {"ok": True, "memo_id": int(cur.lastrowid), "mode": "attendance_memo_created"}
    finally:
        conn.close()
