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
        raise HTTPException(status_code=403, detail="Attendance compliance requires owner or supervisor role.")
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

        start_h, start_m = [int(part) for part in str(start_time).split(":")[:2]]

        in_h, in_m = [int(part) for part in str(actual_in).split(":")[:2]]

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

    return "; ".join(actions) if actions else "No handbook action required"


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
    require_attendance_compliance_user(authorization, x_api_key)
    period_start, period_end = month_bounds(month)
    year_start = f"{month[:4]}-01-01"
    year_end = f"{month[:4]}-12-31"
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employees = fetchall(
            conn,
            """
            SELECT id, employee_code, full_name, department, position
            FROM employees
            WHERE COALESCE(employment_status, 'active') NOT IN ('inactive', 'terminated', 'resigned')
            ORDER BY COALESCE(department, ''), full_name
            """,
        )
        shifts = fetchall(
            conn,
            """
            SELECT id, employee_id, shift_date, start_time, end_time
            FROM scheduled_shifts
            WHERE employee_id IS NOT NULL
              AND date(shift_date) BETWEEN date(?) AND date(?)
            ORDER BY shift_date, start_time
            """,
            (period_start, period_end),
        ) if table_exists(conn, "scheduled_shifts") else []
        actuals = fetchall(
            conn,
            """
            SELECT *
            FROM time_logs
            WHERE date(work_date) BETWEEN date(?) AND date(?)
            """,
            (period_start, period_end),
        ) if table_exists(conn, "time_logs") else []
        year_actuals = fetchall(
            conn,
            """
            SELECT employee_id, absence_type
            FROM time_logs
            WHERE date(work_date) BETWEEN date(?) AND date(?)
              AND absence_type IN ('Unexcused Absence', 'AWOL')
            """,
            (year_start, year_end),
        ) if table_exists(conn, "time_logs") else []
        memos = fetchall(
            conn,
            """
            SELECT am.*, e.full_name, e.employee_code, e.department
            FROM attendance_memos am
            LEFT JOIN employees e ON e.id = am.employee_id
            WHERE am.period_month=?
            ORDER BY am.issued_at DESC, am.id DESC
            """,
            (month,),
        )

        actual_by_key = {(int(row.get("employee_id") or 0), str(row.get("work_date"))[:10]): row for row in actuals if row.get("employee_id")}
        year_counts: dict[int, int] = {}
        for row in year_actuals:
            employee_id = int(row.get("employee_id") or 0)
            year_counts[employee_id] = year_counts.get(employee_id, 0) + 1

        stats: dict[int, dict[str, Any]] = {}
        for employee in employees:
            employee_id = int(employee["id"])
            stats[employee_id] = {
                "employee_id": employee_id,
                "employee_code": employee.get("employee_code"),
                "full_name": employee.get("full_name"),
                "department": employee.get("department"),
                "position": employee.get("position"),
                "scheduled_shifts": 0,
                "missing_logs": 0,
                "late_infractions": 0,
                "partial_absences": 0,
                "unexcused_absences": 0,
                "awol": 0,
                "approved_absences": 0,
                "year_unexcused_infractions": year_counts.get(employee_id, 0),
                "latest_notice": None,
                "latest_evidence": None,
            }

        for shift in shifts:
            employee_id = int(shift.get("employee_id") or 0)
            if employee_id not in stats:
                continue
            item = stats[employee_id]
            item["scheduled_shifts"] += 1
            work_date = str(shift.get("shift_date"))[:10]
            actual = actual_by_key.get((employee_id, work_date))
            if not actual:
                item["missing_logs"] += 1
                continue
            absence_type = str(actual.get("absence_type") or "")
            if int(actual.get("is_absent") or 0):
                if absence_type == "Unexcused Absence":
                    item["unexcused_absences"] += 1
                elif absence_type == "AWOL":
                    item["awol"] += 1
                elif absence_type and absence_type != "Rest Day":
                    item["approved_absences"] += 1
                item["latest_notice"] = actual.get("notice_timing") or item["latest_notice"]
                item["latest_evidence"] = actual.get("evidence_ref") or item["latest_evidence"]
                continue
            minutes = late_minutes(work_date, str(shift.get("start_time") or ""), actual.get("actual_in"))
            if minutes > 5:
                item["late_infractions"] += 1
            if minutes > 30:
                item["partial_absences"] += 1

        items = []
        for item in stats.values():
            item["handbook_action"] = handbook_action(
                int(item["late_infractions"]),
                int(item["partial_absences"]),
                int(item["unexcused_absences"]),
                int(item["awol"]),
            )
            item["attendance_reward_status"] = reward_status(int(item["year_unexcused_infractions"]))
            if any(int(item[key]) for key in ["scheduled_shifts", "missing_logs", "late_infractions", "partial_absences", "unexcused_absences", "awol", "approved_absences"]):
                items.append(item)
        items.sort(key=lambda row: (row["handbook_action"] == "No handbook action required", row.get("department") or "", row.get("full_name") or ""))
        return {"ok": True, "month": month, "period_start": period_start, "period_end": period_end, "items": items, "memos": memos}
    finally:
        conn.close()


@router.post("/attendance/memos")
def create_attendance_memo(
    payload: AttendanceMemoPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_attendance_compliance_user(authorization, x_api_key)
    if payload.status not in {"Draft", "Issued", "Acknowledged", "Voided"}:
        raise HTTPException(status_code=422, detail="Invalid memo status.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")
        timestamp = now_iso()
        cur = conn.execute(
            """
            INSERT INTO attendance_memos(
                employee_id, period_month, memo_type, memo_level, reason, notes,
                status, issued_by, issued_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.employee_id,
                payload.period_month,
                payload.memo_type,
                payload.memo_level,
                payload.reason,
                payload.notes,
                payload.status,
                user.get("display_name"),
                timestamp if payload.status in {"Issued", "Acknowledged"} else None,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        memo = fetchone(conn, "SELECT * FROM attendance_memos WHERE id=?", (int(cur.lastrowid),))
        return {"ok": True, "memo": memo}
    finally:
        conn.close()


@router.post("/attendance/memos/{memo_id}/acknowledge")
def acknowledge_attendance_memo(
    memo_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_attendance_compliance_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        memo = fetchone(conn, "SELECT * FROM attendance_memos WHERE id=?", (memo_id,))
        if not memo:
            raise HTTPException(status_code=404, detail="Memo not found.")
        timestamp = now_iso()
        conn.execute(
            "UPDATE attendance_memos SET status='Acknowledged', acknowledged_by=?, acknowledged_at=?, updated_at=? WHERE id=?",
            (user.get("display_name"), timestamp, timestamp, memo_id),
        )
        conn.commit()
        return {"ok": True, "memo_id": memo_id, "status": "Acknowledged"}
    finally:
        conn.close()
