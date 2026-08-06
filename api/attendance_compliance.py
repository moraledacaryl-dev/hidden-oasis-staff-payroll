from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.security import current_user_from_token, require_api_key
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


def reward_status(year_attendance_infractions: int) -> str:
    if year_attendance_infractions == 0:
        return "Eligible: 2 additional paid leave days next year"
    if 1 <= year_attendance_infractions <= 3:
        return "Eligible: 1 additional paid leave day next year"
    return "Not eligible for attendance-based reward"


def is_excused_attendance_row(row: dict[str, Any]) -> bool:
    marker = " ".join([
        str(row.get("absence_type") or ""),
        str(row.get("attendance_status") or ""),
        str(row.get("notes") or ""),
    ]).lower()

    excused_markers = (
        "excused",
        "approved leave",
        "sick leave",
        "bereavement",
        "sil",
        "service incentive leave",
        "vacation leave",
        "paid leave",
        "corrected log",
    )

    return any(token in marker for token in excused_markers)


@router.get("/attendance/compliance")
def attendance_compliance(
    month: str = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_attendance_compliance_user(authorization, x_api_key)
    period_start, period_end = month_bounds(month)
    year_start = date.fromisoformat(period_start).replace(month=1, day=1).isoformat()
    year_end = date.fromisoformat(period_start).replace(month=12, day=31).isoformat()
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employees = fetchall(
            conn,
            """
            SELECT id, employee_code, full_name, department, position
            FROM employees
            WHERE lower(COALESCE(status, 'active')) NOT IN
                  ('inactive', 'terminated', 'resigned', 'separated')
            ORDER BY COALESCE(department, ''), full_name
            """,
        )
        shifts = fetch_compliance_shifts(conn, period_start, period_end)
        actuals = fetchall(
            conn,
            """
            SELECT *
            FROM time_logs
            WHERE date(work_date) BETWEEN date(?) AND date(?)
            """,
            (period_start, period_end),
        ) if table_exists(conn, "time_logs") else []
        year_shifts = fetch_compliance_shifts(conn, year_start, year_end)
        year_actuals = fetchall(
            conn,
            """
            SELECT *
            FROM time_logs
            WHERE date(work_date) BETWEEN date(?) AND date(?)
            """,
            (year_start, year_end),
        ) if table_exists(conn, "time_logs") else []
        memos = fetchall(
            conn,
            """
            SELECT am.*, e.full_name, e.employee_code, e.department
            FROM attendance_memos am
            LEFT JOIN employees e ON e.id=am.employee_id
            WHERE am.period_month=?
            ORDER BY am.issued_at DESC, am.id DESC
            """,
            (month,),
        )

        actual_by_key = {
            (int(row.get("employee_id") or 0), str(row.get("work_date"))[:10]): row
            for row in actuals
            if row.get("employee_id")
        }
        year_actual_by_key = {
            (int(row.get("employee_id") or 0), str(row.get("work_date"))[:10]): row
            for row in year_actuals
            if row.get("employee_id")
        }

        year_counts: dict[int, int] = {}
        for shift in year_shifts:
            employee_id = int(shift.get("employee_id") or 0)
            if not employee_id:
                continue

            work_date = str(shift.get("shift_date"))[:10]
            actual = year_actual_by_key.get((employee_id, work_date))

            if not actual:
                year_counts[employee_id] = year_counts.get(employee_id, 0) + 1
                continue

            if is_excused_attendance_row(actual):
                continue

            absence_type = str(actual.get("absence_type") or "").strip()
            attendance_status = str(actual.get("attendance_status") or "").strip()
            absence_label = absence_type or attendance_status
            absence_label_lower = absence_label.lower()

            if "unexcused" in absence_label_lower or "awol" in absence_label_lower:
                year_counts[employee_id] = year_counts.get(employee_id, 0) + 1
                continue

            minutes = minutes_late_from_times(
                shift.get("start_time"),
                actual.get("actual_in"),
            )

            if minutes is not None and minutes > 5:
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
                "grace_periods": 0,
                "partial_absences": 0,
                "unexcused_absences": 0,
                "awol": 0,
                "approved_absences": 0,
                "year_unexcused_infractions": year_counts.get(employee_id, 0),
                "latest_notice": None,
                "latest_evidence": None,
                "late_details": [],
                "absence_details": [],
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

            absence_type = str(actual.get("absence_type") or "").strip()
            attendance_status = str(actual.get("attendance_status") or "").strip()
            absence_label = absence_type or attendance_status
            absence_label_lower = absence_label.lower()
            looks_like_absence = (
                int(actual.get("is_absent") or 0) == 1
                or "leave" in absence_label_lower
                or "absence" in absence_label_lower
                or "awol" in absence_label_lower
                or "absent" in absence_label_lower
            )

            if looks_like_absence:
                if "unexcused" in absence_label_lower:
                    item["unexcused_absences"] += 1
                elif "awol" in absence_label_lower:
                    item["awol"] += 1
                elif "rest day" not in absence_label_lower and absence_label:
                    item["approved_absences"] += 1
                item["absence_details"].append({
                    "date": work_date,
                    "type": absence_label or "Absent",
                    "notice": actual.get("notice_timing"),
                    "evidence": actual.get("evidence_ref"),
                })
                item["latest_notice"] = actual.get("notice_timing") or item["latest_notice"]
                item["latest_evidence"] = actual.get("evidence_ref") or item["latest_evidence"]
                continue

            minutes = minutes_late_from_times(
                shift.get("start_time"),
                actual.get("actual_in"),
            )
            late_status = classify_late_minutes(minutes)
            if minutes is not None and 1 <= minutes <= 5:
                item["grace_periods"] += 1
            if minutes is not None and minutes > 5:
                item["late_infractions"] += 1
                item["late_details"].append({
                    "date": work_date,
                    "scheduled_start": shift.get("start_time"),
                    "actual_in": actual.get("actual_in"),
                    "minutes_late": minutes,
                    "status": late_status,
                })
            if minutes is not None and minutes > 30:
                item["partial_absences"] += 1

        items: list[dict[str, Any]] = []
        count_fields = [
            "scheduled_shifts",
            "missing_logs",
            "late_infractions",
            "grace_periods",
            "partial_absences",
            "unexcused_absences",
            "awol",
            "approved_absences",
        ]
        for item in stats.values():
            item["handbook_action"] = handbook_action(
                int(item["late_infractions"]),
                int(item["partial_absences"]),
                int(item["unexcused_absences"]),
                int(item["awol"]),
            )
            item["attendance_reward_status"] = reward_status(
                int(item["year_unexcused_infractions"]),
            )
            if any(int(item[key]) for key in count_fields):
                items.append(item)
        items.sort(key=lambda row: (
            row["handbook_action"] == "No action required",
            row.get("department") or "",
            row.get("full_name") or "",
        ))
        return {
            "ok": True,
            "month": month,
            "period_start": period_start,
            "period_end": period_end,
            "checked_by": user.get("display_name"),
            "items": items,
            "memos": memos,
            "mode": "attendance_compliance_scheduled_shifts_only",
        }
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
