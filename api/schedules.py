from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from api.schedule_change_log import ensure_schedule_change_log_schema, log_schedule_change
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

POSITIONS = {"Receptionist", "Cook", "Barista", "Bartender", "Security", "Housekeeper", "Other"}


class ShiftPayload(BaseModel):
    employee_id: int | None = None
    shift_date: date
    start_time: str
    end_time: str
    position: str = "Other"
    department: str | None = None
    break_minutes: int = 60
    notes: str | None = None


class MoveShiftPayload(BaseModel):
    shift_date: date


class DuplicateShiftPayload(BaseModel):
    shift_date: date | None = None


class CopyWeekPayload(BaseModel):
    from_week_start: date
    to_week_start: date


class DaySchedulePayload(BaseModel):
    shift_id: int | None = None
    employee_id: int | None = None
    shift_date: date
    start_time: str
    end_time: str
    position: str = "Other"
    department: str | None = None
    break_minutes: int = 60
    notes: str | None = None


class DayActualPayload(BaseModel):
    employee_id: int
    shift_date: date
    actual_in: str | None = None
    actual_out: str | None = None
    attendance_status: str = "Pending"
    approved_ot_hours: float = 0
    notes: str | None = None


class DayLeavePayload(BaseModel):
    employee_id: int
    shift_date: date
    leave_kind: str = "None"
    reason: str | None = None
    notice_given_at: str | None = None
    notice_timing: str | None = None
    evidence_ref: str | None = None


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


def attendance_status_from_schedule(start_time: str | None, actual_in: str | None, fallback: str = "Pending") -> str:
    minutes = minutes_late_from_times(start_time, actual_in)
    if minutes is None:
        return fallback
    if minutes <= 0:
        return "ON-TIME"
    if minutes <= 5:
        return "Grace Period"
    if minutes > 30:
        return "Partial Absence"
    return "LATE"



def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def ensure_column(conn, table: str, column: str, definition: str) -> None:
    if column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            position TEXT NOT NULL DEFAULT 'Other',
            department TEXT,
            break_minutes INTEGER NOT NULL DEFAULT 60,
            status TEXT NOT NULL DEFAULT 'Draft',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column(conn, "scheduled_shifts", "legacy_schedule_id", "INTEGER")
    ensure_column(conn, "scheduled_shifts", "source", "TEXT NOT NULL DEFAULT 'planned'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_schedule_ignores (
            legacy_schedule_id INTEGER PRIMARY KEY,
            ignored_by TEXT,
            ignored_at TEXT NOT NULL,
            reason TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_shifts_date ON scheduled_shifts(shift_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_shifts_employee ON scheduled_shifts(employee_id)")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_shifts_legacy_schedule_id
        ON scheduled_shifts(legacy_schedule_id)
        WHERE legacy_schedule_id IS NOT NULL
        """
    )
    if table_exists(conn, "time_logs"):
        ensure_column(conn, "time_logs", "notice_given_at", "TEXT")
        ensure_column(conn, "time_logs", "notice_timing", "TEXT")
        ensure_column(conn, "time_logs", "evidence_ref", "TEXT")
    ensure_schedule_change_log_schema(conn)
    conn.commit()


def hours_for_shift(shift_date: str, start_time: str, end_time: str, break_minutes: int) -> float:
    start = datetime.fromisoformat(f"{shift_date}T{start_time}")
    end = datetime.fromisoformat(f"{shift_date}T{end_time}")
    if end <= start:
        end += timedelta(days=1)
    gross = (end - start).total_seconds() / 3600
    return max(0.0, gross - max(0, break_minutes) / 60)


def clean_shift(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["planned_paid_hours"] = hours_for_shift(str(data.get("shift_date")), str(data.get("start_time")), str(data.get("end_time")), int(data.get("break_minutes") or 0))
    data["is_overnight"] = str(data.get("end_time")) <= str(data.get("start_time"))
    data.setdefault("source", "planned")
    data.setdefault("movable", True)
    return data


def week_bounds(week_start: date) -> tuple[str, str]:
    return week_start.isoformat(), (week_start + timedelta(days=6)).isoformat()


def require_schedule_viewer(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Schedule view requires owner, payroll, or supervisor role.")
    return user


def require_schedule_editor(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Only owner, payroll, or supervisor can edit schedules.")
    return user


def employee_exists(conn, employee_id: int) -> bool:
    return bool(fetchone(conn, "SELECT id FROM employees WHERE id=?", (employee_id,)))


def first_existing(cols: set[str], names: list[str]) -> str | None:
    for name in names:
        if name in cols:
            return name
    return None


def sql_value_expr(cols: set[str], names: list[str], fallback: str, alias: str) -> str:
    col = first_existing(cols, names)
    return f"s.{col} AS {alias}" if col else f"{fallback} AS {alias}"


def schedule_row(conn, shift_id: int | None) -> dict[str, Any] | None:
    if not shift_id:
        return None
    row = fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (shift_id,))
    return dict(row) if row else None


def fetch_legacy_schedule_row(conn, legacy_id: int) -> dict[str, Any] | None:
    if not table_exists(conn, "schedules"):
        return None
    cols = table_columns(conn, "schedules")
    date_col = first_existing(cols, ["work_date", "shift_date", "date", "schedule_date"])
    start_col = first_existing(cols, ["shift_start", "start_time", "time_in", "scheduled_in"])
    end_col = first_existing(cols, ["shift_end", "end_time", "time_out", "scheduled_out"])
    if not date_col or not start_col or not end_col:
        return None
    employee_expr = sql_value_expr(cols, ["employee_id"], "NULL", "employee_id")
    employee_join = "LEFT JOIN employees e ON e.id = s.employee_id" if "employee_id" in cols else ""
    employee_name_expr = "e.full_name AS employee_name" if "employee_id" in cols else "NULL AS employee_name"
    employee_code_expr = "e.employee_code" if "employee_id" in cols else "NULL"
    employee_department_expr = "e.department AS employee_department" if "employee_id" in cols else "NULL AS employee_department"
    position_expr = sql_value_expr(cols, ["position", "role"], "'Other'", "position")
    department_expr = sql_value_expr(cols, ["department", "department_name"], "NULL", "department")
    break_expr = sql_value_expr(cols, ["break_minutes", "break_mins", "unpaid_break_minutes"], "60", "break_minutes")
    notes_expr = sql_value_expr(cols, ["notes", "note"], "NULL", "notes")
    row = fetchone(
        conn,
        f"""
        SELECT s.id AS legacy_id, {employee_expr}, s.{date_col} AS shift_date,
               s.{start_col} AS start_time, s.{end_col} AS end_time,
               {position_expr}, {department_expr}, {break_expr}, {notes_expr},
               {employee_name_expr}, {employee_code_expr} AS employee_code, {employee_department_expr}
        FROM schedules s
        {employee_join}
        WHERE s.id=?
        """,
        (legacy_id,),
    )
    if not row:
        return None
    data = dict(row)
    data["id"] = -int(data.get("legacy_id") or 0)
    data["source"] = "imported"
    data["movable"] = False
    data["position"] = data.get("position") or "Other"
    data["break_minutes"] = int(data.get("break_minutes") or 0)
    return clean_shift(data)


def fetch_legacy_schedule_rows(conn, start: str, end: str) -> list[dict[str, Any]]:
    if not table_exists(conn, "schedules"):
        return []
    cols = table_columns(conn, "schedules")
    date_col = first_existing(cols, ["work_date", "shift_date", "date", "schedule_date"])
    start_col = first_existing(cols, ["shift_start", "start_time", "time_in", "scheduled_in"])
    end_col = first_existing(cols, ["shift_end", "end_time", "time_out", "scheduled_out"])
    if not date_col or not start_col or not end_col:
        return []
    employee_expr = sql_value_expr(cols, ["employee_id"], "NULL", "employee_id")
    employee_join = "LEFT JOIN employees e ON e.id = s.employee_id" if "employee_id" in cols else ""
    employee_name_expr = "e.full_name AS employee_name" if "employee_id" in cols else "NULL AS employee_name"
    employee_code_expr = "e.employee_code" if "employee_id" in cols else "NULL"
    employee_department_expr = "e.department AS employee_department" if "employee_id" in cols else "NULL AS employee_department"
    employee_order_expr = "COALESCE(e.full_name, 'Unassigned')" if "employee_id" in cols else "'Unassigned'"
    position_expr = sql_value_expr(cols, ["position", "role"], "'Other'", "position")
    department_expr = sql_value_expr(cols, ["department", "department_name"], "NULL", "department")
    break_expr = sql_value_expr(cols, ["break_minutes", "break_mins", "unpaid_break_minutes"], "60", "break_minutes")
    notes_expr = sql_value_expr(cols, ["notes", "note"], "NULL", "notes")
    status_expr = sql_value_expr(cols, ["status"], "'Imported'", "status")
    rows = fetchall(
        conn,
        f"""
        SELECT s.id AS legacy_id, {employee_expr}, s.{date_col} AS shift_date,
               s.{start_col} AS start_time, s.{end_col} AS end_time,
               {position_expr}, {department_expr}, {break_expr}, {notes_expr}, {status_expr},
               {employee_name_expr}, {employee_code_expr} AS employee_code, {employee_department_expr}
        FROM schedules s
        {employee_join}
        LEFT JOIN scheduled_shifts ss ON ss.legacy_schedule_id = s.id
        LEFT JOIN legacy_schedule_ignores lsi ON lsi.legacy_schedule_id = s.id
        WHERE date(s.{date_col}) BETWEEN date(?) AND date(?)
          AND ss.id IS NULL
          AND lsi.legacy_schedule_id IS NULL
        ORDER BY s.{date_col}, s.{start_col}, {employee_order_expr}
        """,
        (start, end),
    )
    imported: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["id"] = -int(data.get("legacy_id") or 0)
        data["source"] = "imported"
        data["movable"] = False
        data["position"] = data.get("position") or "Other"
        data["break_minutes"] = int(data.get("break_minutes") or 0)
        imported.append(clean_shift(data))
    return imported


def migrate_legacy_schedule_row(conn, legacy_id: int, actor: str | None) -> int:
    existing = fetchone(conn, "SELECT id FROM scheduled_shifts WHERE legacy_schedule_id=?", (legacy_id,))
    if existing:
        return int(existing["id"])
    legacy = fetch_legacy_schedule_row(conn, legacy_id)
    if not legacy:
        raise HTTPException(status_code=404, detail="Legacy schedule row not found.")
    employee_id = int(legacy.get("employee_id") or 0) or None
    position = str(legacy.get("position") or "Other")
    if position not in POSITIONS:
        position = "Other"
    timestamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO scheduled_shifts(
            employee_id, shift_date, start_time, end_time, position, department,
            break_minutes, status, notes, legacy_schedule_id, source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, ?, 'planned', ?, ?)
        """,
        (
            employee_id,
            str(legacy.get("shift_date"))[:10],
            str(legacy.get("start_time"))[:5],
            str(legacy.get("end_time"))[:5],
            position,
            legacy.get("department") or legacy.get("employee_department"),
            int(legacy.get("break_minutes") or 0),
            legacy.get("notes"),
            legacy_id,
            timestamp,
            timestamp,
        ),
    )
    shift_id = int(cur.lastrowid)
    log_schedule_change(
        conn,
        change_type="migrate_legacy_schedule",
        entity_type="scheduled_shift",
        entity_id=shift_id,
        employee_id=employee_id,
        work_date=str(legacy.get("shift_date"))[:10],
        before=legacy,
        after=schedule_row(conn, shift_id),
        changed_by=actor,
    )
    return shift_id


def fetch_shift(conn, shift_id: int | None, employee_id: int | None, shift_date: str) -> dict[str, Any] | None:
    if shift_id and shift_id > 0:
        return fetchone(
            conn,
            """
            SELECT ss.*, e.full_name AS employee_name, e.employee_code, e.department AS employee_department
            FROM scheduled_shifts ss
            LEFT JOIN employees e ON e.id = ss.employee_id
            WHERE ss.id=?
            """,
            (shift_id,),
        )
    if employee_id:
        return fetchone(
            conn,
            """
            SELECT ss.*, e.full_name AS employee_name, e.employee_code, e.department AS employee_department
            FROM scheduled_shifts ss
            LEFT JOIN employees e ON e.id = ss.employee_id
            WHERE ss.employee_id=? AND date(ss.shift_date)=date(?)
            ORDER BY ss.start_time, ss.id
            LIMIT 1
            """,
            (employee_id, shift_date),
        )
    return None


def fetch_time_log(conn, employee_id: int | None, shift_date: str) -> dict[str, Any] | None:
    if not employee_id:
        return None
    return fetchone(
        conn,
        """
        SELECT * FROM time_logs
        WHERE employee_id=? AND date(work_date)=date(?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (employee_id, shift_date),
    )


def fetch_leave(conn, employee_id: int | None, shift_date: str) -> dict[str, Any] | None:
    if not employee_id or not table_exists(conn, "leave_requests"):
        return None
    return fetchone(
        conn,
        """
        SELECT lr.*, lt.name AS leave_type_name
        FROM leave_requests lr
        LEFT JOIN leave_types lt ON lt.id = lr.leave_type_id
        WHERE lr.employee_id=?
          AND date(?) BETWEEN date(lr.start_date) AND date(lr.end_date)
          AND lower(COALESCE(lr.status, '')) NOT IN ('rejected', 'declined', 'cancelled', 'canceled', 'void')
        ORDER BY lr.id DESC
        LIMIT 1
        """,
        (employee_id, shift_date),
    )


def paid_run_for_day(conn, shift_date: str) -> dict[str, Any] | None:
    return fetchone(
        conn,
        """
        SELECT id, status, period_start, period_end, paid_at
        FROM payroll_runs
        WHERE date(?) BETWEEN date(period_start) AND date(period_end)
          AND (status IN ('Paid', 'Released') OR paid_at IS NOT NULL)
        ORDER BY paid_at DESC, id DESC
        LIMIT 1
        """,
        (shift_date,),
    )


def day_bundle(conn, shift_date: str, employee_id: int | None = None, shift_id: int | None = None) -> dict[str, Any]:
    ensure_schema(conn)
    shift = fetch_legacy_schedule_row(conn, abs(shift_id)) if shift_id and shift_id < 0 else fetch_shift(conn, shift_id, employee_id, shift_date)
    resolved_employee_id = employee_id or (int(shift["employee_id"]) if shift and shift.get("employee_id") else None)
    employee = fetchone(conn, "SELECT id, full_name, employee_code, department, position FROM employees WHERE id=?", (resolved_employee_id,)) if resolved_employee_id else None
    locked_run = paid_run_for_day(conn, shift_date)
    return {
        "ok": True,
        "employee": employee,
        "shift": clean_shift({**shift, "source": shift.get("source") or "planned", "movable": shift.get("movable", True)}) if shift else None,
        "actual": fetch_time_log(conn, resolved_employee_id, shift_date),
        "leave": fetch_leave(conn, resolved_employee_id, shift_date),
        "payroll_locked": bool(locked_run),
        "paid_run": locked_run,
        "legacy_read_only": False,
        "message": None,
    }


def assert_not_paid_locked(conn, shift_date: str) -> None:
    return None


def ensure_leave_type(conn, name: str, paid: int) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_credits REAL NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 1,
            statutory INTEGER NOT NULL DEFAULT 0,
            requires_approval INTEGER NOT NULL DEFAULT 1,
            requires_attachment INTEGER NOT NULL DEFAULT 0,
            annual_reset INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT
        )
        """
    )
    row = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (name,))
    if row:
        return int(row["id"])
    cur = conn.execute("INSERT INTO leave_types(name, paid, active, notes) VALUES(?, ?, 1, 'Created from schedule day editor')", (name, paid))
    return int(cur.lastrowid)


@router.get("/schedules/employees")
def schedule_employees(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_schedule_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        cols = table_columns(conn, "employees")
        name_col = "full_name" if "full_name" in cols else "name"
        code_expr = "employee_code" if "employee_code" in cols else "'' AS employee_code"
        dept_expr = "department" if "department" in cols else "'' AS department"
        position_expr = "position" if "position" in cols else "'' AS position"
        status_expr = "employment_status" if "employment_status" in cols else "'active' AS employment_status"
        where = "WHERE COALESCE(employment_status, 'active') NOT IN ('inactive', 'terminated', 'resigned')" if "employment_status" in cols else ""
        rows = fetchall(conn, f"SELECT id, {name_col} AS full_name, {code_expr}, {dept_expr}, {position_expr}, {status_expr} FROM employees {where} ORDER BY COALESCE(department, ''), {name_col}")
        return {"ok": True, "items": rows}
    finally:
        conn.close()


@router.get("/schedules/week")
def schedule_week(week_start: date = Query(...), authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_schedule_viewer(authorization, x_api_key)
    start, end = week_bounds(week_start)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        rows = fetchall(
            conn,
            """
            SELECT ss.*, e.full_name AS employee_name, e.employee_code, e.department AS employee_department
            FROM scheduled_shifts ss
            LEFT JOIN employees e ON e.id = ss.employee_id
            WHERE date(ss.shift_date) BETWEEN date(?) AND date(?)
            ORDER BY ss.shift_date, ss.start_time, COALESCE(e.full_name, 'Unassigned')
            """,
            (start, end),
        )
        planned = [clean_shift({**row, "source": row.get("source") or "planned", "movable": True}) for row in rows]
        imported = fetch_legacy_schedule_rows(conn, start, end)
        items = sorted(planned + imported, key=lambda row: (str(row.get("shift_date")), str(row.get("start_time")), str(row.get("employee_name") or "")))
        return {"ok": True, "week_start": start, "week_end": end, "items": items, "mode": "canonical_schedule_with_legacy_overlay"}
    finally:
        conn.close()


@router.get("/schedules/day")
def schedule_day(shift_date: date = Query(...), employee_id: int | None = Query(default=None), shift_id: int | None = Query(default=None), authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_schedule_viewer(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        return day_bundle(conn, shift_date.isoformat(), employee_id, shift_id)
    finally:
        conn.close()


@router.post("/schedules/shifts")
def create_shift(payload: ShiftPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    if payload.position not in POSITIONS:
        raise HTTPException(status_code=422, detail="Invalid position.")
    employee_id = payload.employee_id if payload.employee_id and payload.employee_id > 0 else None
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if employee_id and not employee_exists(conn, employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        timestamp = now_iso()
        cur = conn.execute(
            """
            INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, notes, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)
            """,
            (employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, payload.break_minutes, payload.notes, timestamp, timestamp),
        )
        shift_id = int(cur.lastrowid)
        after = schedule_row(conn, shift_id)
        log_schedule_change(conn, change_type="create_schedule", entity_type="scheduled_shift", entity_id=shift_id, employee_id=employee_id, work_date=payload.shift_date.isoformat(), before=None, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return {"ok": True, "shift": clean_shift(after or {}), "mode": "planned_schedule_only"}
    finally:
        conn.close()


@router.post("/schedules/day/scheduled")
def save_day_schedule(payload: DaySchedulePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    if payload.position not in POSITIONS:
        raise HTTPException(status_code=422, detail="Invalid position.")
    employee_id = payload.employee_id if payload.employee_id and payload.employee_id > 0 else None
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if payload.shift_id and payload.shift_id < 0:
            payload.shift_id = migrate_legacy_schedule_row(conn, abs(payload.shift_id), user.get("display_name"))
        if employee_id and not employee_exists(conn, employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        timestamp = now_iso()
        before = schedule_row(conn, payload.shift_id) if payload.shift_id else None
        if payload.shift_id:
            row = schedule_row(conn, payload.shift_id)
            if not row:
                raise HTTPException(status_code=404, detail="Shift not found.")
            conn.execute(
                """
                UPDATE scheduled_shifts
                SET employee_id=?, shift_date=?, start_time=?, end_time=?, position=?, department=?, break_minutes=?, notes=?, updated_at=?
                WHERE id=?
                """,
                (employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, int(payload.break_minutes or 0), payload.notes, timestamp, payload.shift_id),
            )
            shift_id = payload.shift_id
        else:
            cur = conn.execute(
                """
                INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, 'planned', ?, ?)
                """,
                (employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, int(payload.break_minutes or 0), payload.notes, timestamp, timestamp),
            )
            shift_id = int(cur.lastrowid)
        after = schedule_row(conn, int(shift_id))
        log_schedule_change(conn, change_type="update_schedule" if before else "create_schedule", entity_type="scheduled_shift", entity_id=int(shift_id), employee_id=employee_id, work_date=payload.shift_date.isoformat(), before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return day_bundle(conn, payload.shift_date.isoformat(), employee_id, int(shift_id)) | {"message": "Scheduled shift saved. Existing payroll runs were not changed."}
    finally:
        conn.close()


@router.post("/schedules/day/actual")
def save_day_actual(payload: DayActualPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    shift_date = payload.shift_date.isoformat()
    status_value = payload.attendance_status.strip() or "Pending"
    if status_value not in {"Pending", "Approved", "Needs Review", "Needs Correction", "Rejected", "ON-TIME", "Grace Period", "LATE", "Partial Absence"}:
        raise HTTPException(status_code=422, detail="Invalid attendance status.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not employee_exists(conn, payload.employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        timestamp = now_iso()
        shift = fetch_shift(conn, None, payload.employee_id, shift_date)
        if status_value in {"Pending", "ON-TIME", "Grace Period", "LATE", "Partial Absence"}:
            status_value = attendance_status_from_schedule(
                str(shift.get("start_time") or "") if shift else None,
                payload.actual_in,
                fallback=status_value,
            )
        existing = fetch_time_log(conn, payload.employee_id, shift_date)
        before = dict(existing) if existing else None
        if existing:
            conn.execute(
                """
                UPDATE time_logs
                SET actual_in=?, actual_out=?, is_absent=0, absence_type=NULL, attendance_status=?, approved_ot_hours=?, reviewed_by=?, reviewed_at=?, notes=?, updated_at=?
                WHERE id=?
                """,
                (payload.actual_in, payload.actual_out, status_value, float(payload.approved_ot_hours or 0), user.get("display_name"), timestamp, payload.notes, timestamp, existing["id"]),
            )
            log_id = int(existing["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type, is_absent, detected_ot_hours, approved_ot_hours, ot_status, attendance_status, reviewed_by, reviewed_at, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'manual', 'Manual', 0, 0, ?, 'None', ?, ?, ?, ?, ?, ?)
                """,
                (payload.employee_id, shift_date, payload.actual_in, payload.actual_out, float(payload.approved_ot_hours or 0), status_value, user.get("display_name"), timestamp, payload.notes, timestamp, timestamp),
            )
            log_id = int(cur.lastrowid)
        after = dict(fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (log_id,)) or {})
        log_schedule_change(conn, change_type="update_actual" if before else "create_actual", entity_type="time_log", entity_id=log_id, employee_id=payload.employee_id, work_date=shift_date, before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return day_bundle(conn, shift_date, payload.employee_id) | {"message": "Actual attendance saved."}
    finally:
        conn.close()


@router.post("/schedules/day/leave")
def save_day_leave(payload: DayLeavePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    shift_date = payload.shift_date.isoformat()
    leave_kind = payload.leave_kind.strip() or "None"
    allowed = {
        "None",
        "Rest Day",
        "Approved / Excused Absence",
        "Unexcused Absence",
        "AWOL",
        "Sick Leave",
        "Emergency Leave",
        "Bereavement Leave",
        "Official Business",
        "Other Approved Absence",
    }
    if leave_kind not in allowed:
        raise HTTPException(status_code=422, detail="Invalid leave or absence type.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not employee_exists(conn, payload.employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        timestamp = now_iso()
        existing_log = fetch_time_log(conn, payload.employee_id, shift_date)
        before = dict(existing_log) if existing_log else None
        if leave_kind == "None":
            if existing_log:
                conn.execute("UPDATE time_logs SET is_absent=0, absence_type=NULL, updated_at=? WHERE id=?", (timestamp, existing_log["id"]))
                log_id = int(existing_log["id"])
            else:
                log_id = None
        else:
            is_infraction_absence = leave_kind in {"Unexcused Absence", "AWOL"}
            attendance_status = "Needs Review" if is_infraction_absence else "Approved"
            notice_given_at = None if leave_kind == "AWOL" else payload.notice_given_at
            notice_timing = "No notice" if leave_kind == "AWOL" else (payload.notice_timing or None)

            if existing_log:
                conn.execute(
                    """
                    UPDATE time_logs
                    SET is_absent=1,
                        absence_type=?,
                        attendance_status=?,
                        reviewed_by=?,
                        reviewed_at=?,
                        notes=?,
                        notice_given_at=?,
                        notice_timing=?,
                        evidence_ref=?,
                        updated_at=?
                    WHERE id=?
                    """,
                    (
                        leave_kind,
                        attendance_status,
                        user.get("display_name"),
                        timestamp,
                        payload.reason,
                        notice_given_at,
                        notice_timing,
                        payload.evidence_ref,
                        timestamp,
                        existing_log["id"],
                    ),
                )
                log_id = int(existing_log["id"])
            else:
                cur = conn.execute(
                    """
                    INSERT INTO time_logs(
                        employee_id, work_date, source, verification_type,
                        is_absent, absence_type, detected_ot_hours, approved_ot_hours,
                        ot_status, attendance_status, reviewed_by, reviewed_at,
                        notes, notice_given_at, notice_timing, evidence_ref,
                        created_at, updated_at
                    )
                    VALUES (?, ?, 'manual', 'Manual', 1, ?, 0, 0, 'None', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.employee_id,
                        shift_date,
                        leave_kind,
                        attendance_status,
                        user.get("display_name"),
                        timestamp,
                        payload.reason,
                        notice_given_at,
                        notice_timing,
                        payload.evidence_ref,
                        timestamp,
                        timestamp,
                    ),
                )
                log_id = int(cur.lastrowid)

            if leave_kind in {"Sick Leave", "Emergency Leave", "Bereavement Leave", "Official Business", "Other Approved Absence"}:
                paid = 0 if leave_kind == "Emergency Leave" else 1
                leave_type_id = ensure_leave_type(conn, leave_kind, paid)
                existing_leave = fetch_leave(conn, payload.employee_id, shift_date)
                if existing_leave:
                    conn.execute(
                        "UPDATE leave_requests SET leave_type_id=?, start_date=?, end_date=?, days=1, paid=?, status='Approved', reason=?, reviewed_by=?, reviewed_at=? WHERE id=?",
                        (leave_type_id, shift_date, shift_date, paid, payload.reason, user.get("display_name"), timestamp, existing_leave["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, reviewed_by, reviewed_at, created_at) VALUES (?, ?, ?, ?, 1, ?, 'Approved', ?, ?, ?, ?)",
                        (payload.employee_id, leave_type_id, shift_date, shift_date, paid, payload.reason, user.get("display_name"), timestamp, timestamp),
                    )
        if log_id:
            after = dict(fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (log_id,)) or {})
            log_schedule_change(conn, change_type="update_absence" if before else "create_absence", entity_type="time_log", entity_id=log_id, employee_id=payload.employee_id, work_date=shift_date, before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return day_bundle(conn, shift_date, payload.employee_id) | {"message": "Leave/absence saved."}
    finally:
        conn.close()


@router.post("/schedules/shifts/{shift_id}/move")
def move_shift(shift_id: int, payload: MoveShiftPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        before = schedule_row(conn, shift_id)
        if not before:
            raise HTTPException(status_code=404, detail="Shift not found.")
        conn.execute("UPDATE scheduled_shifts SET shift_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (payload.shift_date.isoformat(), shift_id))
        after = schedule_row(conn, shift_id)
        log_schedule_change(conn, change_type="move_schedule", entity_type="scheduled_shift", entity_id=shift_id, employee_id=int(after.get("employee_id") or 0) if after else None, work_date=payload.shift_date.isoformat(), before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return {"ok": True, "shift": clean_shift(after or {}), "mode": "planned_shift_moved_not_payroll"}
    finally:
        conn.close()


@router.post("/schedules/shifts/{shift_id}/delete")
def delete_shift(shift_id: int, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if shift_id < 0:
            legacy_id = abs(shift_id)
            legacy = fetch_legacy_schedule_row(conn, legacy_id)
            if not legacy:
                raise HTTPException(status_code=404, detail="Legacy schedule row not found.")
            conn.execute("INSERT OR REPLACE INTO legacy_schedule_ignores(legacy_schedule_id, ignored_by, ignored_at, reason) VALUES (?, ?, ?, ?)", (legacy_id, user.get("display_name"), now_iso(), "Deleted from schedule page"))
            log_schedule_change(conn, change_type="delete_legacy_schedule", entity_type="legacy_schedule", entity_id=legacy_id, employee_id=int(legacy.get("employee_id") or 0) or None, work_date=str(legacy.get("shift_date"))[:10], before=legacy, after=None, changed_by=user.get("display_name"))
            conn.commit()
            return {"ok": True, "deleted_shift_id": shift_id, "mode": "legacy_shift_hidden_payroll_snapshot_unchanged"}
        before = schedule_row(conn, shift_id)
        if not before:
            raise HTTPException(status_code=404, detail="Shift not found.")
        conn.execute("DELETE FROM scheduled_shifts WHERE id=?", (shift_id,))
        log_schedule_change(conn, change_type="delete_schedule", entity_type="scheduled_shift", entity_id=shift_id, employee_id=int(before.get("employee_id") or 0) or None, work_date=str(before.get("shift_date"))[:10], before=before, after=None, changed_by=user.get("display_name"))
        conn.commit()
        return {"ok": True, "deleted_shift_id": shift_id, "mode": "historical_shift_deleted_payroll_snapshot_unchanged"}
    finally:
        conn.close()


@router.post("/schedules/shifts/{shift_id}/duplicate")
def duplicate_shift(shift_id: int, payload: DuplicateShiftPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        before = schedule_row(conn, shift_id)
        if not before:
            raise HTTPException(status_code=404, detail="Shift not found.")
        target_date = payload.shift_date.isoformat() if payload.shift_date else str(before.get("shift_date"))
        cur = conn.execute("INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, 'planned', ?, ?)", (before.get("employee_id"), target_date, before.get("start_time"), before.get("end_time"), before.get("position") or "Other", before.get("department"), int(before.get("break_minutes") or 0), before.get("notes"), now_iso(), now_iso()))
        new_id = int(cur.lastrowid)
        after = schedule_row(conn, new_id)
        log_schedule_change(conn, change_type="duplicate_schedule", entity_type="scheduled_shift", entity_id=new_id, employee_id=int(after.get("employee_id") or 0) if after else None, work_date=target_date, before=None, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return {"ok": True, "shift": clean_shift(after or {}), "mode": "planned_shift_duplicated_not_payroll"}
    finally:
        conn.close()


@router.post("/schedules/copy-week")
def copy_week(payload: CopyWeekPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    source_start, source_end = week_bounds(payload.from_week_start)
    target_start = payload.to_week_start
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        rows = fetchall(conn, "SELECT * FROM scheduled_shifts WHERE date(shift_date) BETWEEN date(?) AND date(?) ORDER BY shift_date, start_time", (source_start, source_end))
        copied = 0
        for row in rows:
            source_date = date.fromisoformat(str(row["shift_date"]))
            target_date = (target_start + timedelta(days=(source_date - payload.from_week_start).days)).isoformat()
            cur = conn.execute("INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, 'planned', ?, ?)", (row.get("employee_id"), target_date, row.get("start_time"), row.get("end_time"), row.get("position") or "Other", row.get("department"), int(row.get("break_minutes") or 0), row.get("notes"), now_iso(), now_iso()))
            new_id = int(cur.lastrowid)
            log_schedule_change(conn, change_type="copy_week_schedule", entity_type="scheduled_shift", entity_id=new_id, employee_id=int(row.get("employee_id") or 0) or None, work_date=target_date, before=None, after=schedule_row(conn, new_id), changed_by=user.get("display_name"))
            copied += 1
        conn.commit()
        return {"ok": True, "copied": copied, "mode": "planned_week_copied_not_payroll"}
    finally:
        conn.close()
