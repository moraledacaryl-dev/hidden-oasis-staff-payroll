from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from core.audit import log_audit
from core.db import DB_PATH, fetchall, get_conn, now_iso
from core.schedule_source import trusted_schedule_rows

router = APIRouter(prefix="/api/v1")
DEFAULT_VARIANCE_MINUTES = 30
MAX_TEMPLATE_ROWS = 20_000
TEMPLATE_SOURCES = ("template_upload", "attendance_template")

TEMPLATE_COLUMNS = [
    "work_date",
    "employee_name",
    "biometric_id",
    "time_in",
    "time_out",
    "time_out_date",
    "break_minutes",
    "attendance_status",
    "remarks",
    "is_absent",
    "is_halfday",
    "is_ot",
    "ot_hours",
    "ot_reason",
    "needs_review",
    "review_note",
]


class AttendanceTemplateRow(BaseModel):
    work_date: str
    employee_name: str | None = None
    biometric_id: str | None = None
    time_in: str | None = None
    time_out: str | None = None
    time_out_date: str | None = None
    break_minutes: int | None = None
    attendance_status: str | None = None
    remarks: str | None = None
    is_absent: int | bool | str | None = None
    is_halfday: int | bool | str | None = None
    is_ot: int | bool | str | None = None
    ot_hours: float | str | None = None
    ot_reason: str | None = None
    needs_review: int | bool | str | None = None
    review_note: str | None = None


class AttendanceTemplateImportPayload(BaseModel):
    rows: list[AttendanceTemplateRow]
    dry_run: bool = True
    file_name: str | None = None
    replace_template_rows: bool = True


def require_attendance_importer(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can import attendance.")
    return user


def clean(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y", "x", "review", "needs review"}


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def parse_work_date(value: str) -> str:
    raw = clean(value)
    if not raw:
        raise ValueError("work_date is required.")
    for fmt in ("%Y-%m-%d", "%m-%d-%y", "%m/%d/%y", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return date.fromisoformat(raw).isoformat()


def parse_time(value: str | None) -> str | None:
    raw = clean(value)
    if not raw:
        return None
    raw = raw.replace(".", ":").upper()
    raw = re.sub(r"\s+", " ", raw)
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"):
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError(f"Invalid time: {value}")


def parse_float(value: Any, default: float = 0.0) -> float:
    raw = clean(value)
    if not raw:
        return default
    return float(raw)


def employee_lookup(conn) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = fetchall(
        conn,
        """
        SELECT id, employee_code, full_name, status
        FROM employees
        WHERE COALESCE(status, 'Active') != 'Inactive'
        """,
    )
    by_code = {clean(row.get("employee_code")).lower(): row for row in rows if clean(row.get("employee_code"))}
    by_name = {normalize_name(clean(row.get("full_name"))): row for row in rows if clean(row.get("full_name"))}
    return by_code, by_name


def resolve_employee(row: AttendanceTemplateRow, by_code: dict[str, dict[str, Any]], by_name: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    biometric_id = clean(row.biometric_id)
    employee_name = clean(row.employee_name)
    employee: dict[str, Any] | None = None

    if biometric_id:
        employee = by_code.get(biometric_id.lower())
        if not employee:
            issues.append(f"Biometric/employee code not found: {biometric_id}")

    if employee_name:
        by_name_match = by_name.get(normalize_name(employee_name))
        if employee and by_name_match and int(employee["id"]) != int(by_name_match["id"]):
            issues.append("Biometric ID and employee name point to different employees.")
        if not employee:
            employee = by_name_match
        if not by_name_match and not biometric_id:
            issues.append(f"Employee name not found: {employee_name}")

    if not biometric_id and not employee_name:
        issues.append("Either employee_name or biometric_id is required.")

    return employee, issues


def build_notes(row: AttendanceTemplateRow, time_out_date: str | None, work_date: str, issues: list[str]) -> str:
    notes: list[str] = []
    remarks = clean(row.remarks)
    review_note = clean(row.review_note)
    if remarks:
        notes.append(remarks)
    if truthy(row.is_halfday):
        notes.append("HALFDAY")
    if truthy(row.is_ot):
        reason = clean(row.ot_reason)
        notes.append(f"OT: {reason}" if reason else "OT")
    if time_out_date and time_out_date != work_date:
        notes.append(f"time_out_date={time_out_date}")
    if review_note:
        notes.append(f"Review: {review_note}")
    if issues:
        notes.append("Import flags: " + "; ".join(issues))
    return " | ".join(notes)


def validate_template_row(row: AttendanceTemplateRow, by_code: dict[str, dict[str, Any]], by_name: dict[str, dict[str, Any]], row_number: int) -> dict[str, Any]:
    issues: list[str] = []
    try:
        work_date = parse_work_date(row.work_date)
    except Exception as exc:
        work_date = ""
        issues.append(str(exc))

    try:
        actual_in = parse_time(row.time_in)
    except ValueError as exc:
        actual_in = None
        issues.append(str(exc))

    try:
        actual_out = parse_time(row.time_out)
    except ValueError as exc:
        actual_out = None
        issues.append(str(exc))

    try:
        time_out_date = parse_work_date(row.time_out_date) if clean(row.time_out_date) else work_date
    except Exception as exc:
        time_out_date = work_date
        issues.append(f"Invalid time_out_date: {exc}")

    employee, employee_issues = resolve_employee(row, by_code, by_name)
    issues.extend(employee_issues)

    is_absent = 1 if truthy(row.is_absent) else 0
    if actual_in and not actual_out:
        issues.append("Missing time_out.")
    if actual_out and not actual_in:
        issues.append("Missing time_in.")
    if actual_in and actual_out and time_out_date == work_date and actual_out < actual_in:
        issues.append("time_out is earlier than time_in; set time_out_date to the next day for overnight shifts.")

    try:
        ot_hours = parse_float(row.ot_hours)
    except ValueError:
        ot_hours = 0.0
        issues.append("Invalid ot_hours.")

    return {
        "row_number": row_number,
        "employee_id": int(employee["id"]) if employee else None,
        "employee_name": employee.get("full_name") if employee else clean(row.employee_name),
        "employee_code": employee.get("employee_code") if employee else clean(row.biometric_id),
        "work_date": work_date,
        "actual_in": actual_in,
        "actual_out": actual_out,
        "time_out_date": time_out_date,
        "is_absent": is_absent,
        "requested_ot_hours": max(0.0, ot_hours) if truthy(row.is_ot) else 0.0,
        "attendance_status": "Error" if issues else "Pending classification",
        "needs_review": 0,
        "review_reason": None,
        "classification": "error" if issues else "pending",
        "skip_reason": None,
        "issues": issues,
        "notes": build_notes(row, time_out_date, work_date, issues),
    }


def variance_limit_minutes() -> int:
    raw = os.getenv("STAFF_PAYROLL_ATTENDANCE_VARIANCE_MINUTES", str(DEFAULT_VARIANCE_MINUTES))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_VARIANCE_MINUTES


def shift_interval(work_date: str, start_time: str, end_time: str) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(f"{work_date}T{start_time[:5]}")
    end = datetime.fromisoformat(f"{work_date}T{end_time[:5]}")
    if end <= start:
        end += timedelta(days=1)
    return start, end


def scheduled_interval(shifts: list[dict[str, Any]]) -> tuple[datetime, datetime] | None:
    if not shifts:
        return None
    intervals = [
        shift_interval(str(shift["work_date"]), str(shift["shift_start"]), str(shift["shift_end"]))
        for shift in shifts
    ]
    return min(item[0] for item in intervals), max(item[1] for item in intervals)


def actual_interval(row: dict[str, Any]) -> tuple[datetime, datetime] | None:
    if not row.get("actual_in") or not row.get("actual_out"):
        return None
    start = datetime.fromisoformat(f"{row['work_date']}T{row['actual_in']}")
    end_date = str(row.get("time_out_date") or row["work_date"])
    end = datetime.fromisoformat(f"{end_date}T{row['actual_out']}")
    return start, end


def rest_day_keys(conn, period_start: str, period_end: str) -> set[tuple[int, str]]:
    rows = fetchall(
        conn,
        """
        SELECT employee_id, work_date
        FROM schedule_day_markers
        WHERE marker_type='Rest Day' AND active=1
          AND date(work_date) BETWEEN date(?) AND date(?)
        """,
        (period_start, period_end),
    )
    return {(int(row["employee_id"]), str(row["work_date"])) for row in rows}


def approved_leave_spans(conn, period_start: str, period_end: str) -> dict[int, list[tuple[str, str]]]:
    spans: dict[int, list[tuple[str, str]]] = defaultdict(list)
    rows = fetchall(
        conn,
        """
        SELECT employee_id, start_date, end_date
        FROM leave_requests
        WHERE status='Approved'
          AND date(start_date) <= date(?)
          AND date(end_date) >= date(?)
        """,
        (period_end, period_start),
    )
    for row in rows:
        spans[int(row["employee_id"])].append((str(row["start_date"]), str(row["end_date"])))
    return spans


def manual_attendance_keys(conn, period_start: str, period_end: str) -> set[tuple[int, str]]:
    placeholders = ",".join("?" for _ in TEMPLATE_SOURCES)
    rows = fetchall(
        conn,
        f"""
        SELECT employee_id, work_date
        FROM time_logs
        WHERE date(work_date) BETWEEN date(?) AND date(?)
          AND source NOT IN ({placeholders})
          AND COALESCE(attendance_status, '') != 'Rejected'
        """,
        (period_start, period_end, *TEMPLATE_SOURCES),
    )
    return {(int(row["employee_id"]), str(row["work_date"])) for row in rows}


def apply_attendance_triage(conn, rows: list[dict[str, Any]]) -> int:
    valid_dates = [str(row["work_date"]) for row in rows if row.get("employee_id") and row.get("work_date")]
    if not valid_dates:
        return variance_limit_minutes()
    period_start = min(valid_dates)
    period_end = max(valid_dates)
    schedules: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for shift in trusted_schedule_rows(conn, period_start, period_end):
        schedules[(int(shift["employee_id"]), str(shift["work_date"]))].append(shift)
    rest_days = rest_day_keys(conn, period_start, period_end)
    leave_spans = approved_leave_spans(conn, period_start, period_end)
    manual_keys = manual_attendance_keys(conn, period_start, period_end)
    variance_minutes = variance_limit_minutes()
    seen: set[tuple[int, str]] = set()

    for row in rows:
        if not row.get("employee_id") or not row.get("work_date") or row["issues"]:
            row["classification"] = "error"
            row["attendance_status"] = "Error"
            continue

        key = (int(row["employee_id"]), str(row["work_date"]))
        if key in seen:
            row["issues"].append("Duplicate employee and work_date.")
            row["classification"] = "error"
            row["attendance_status"] = "Error"
            continue
        seen.add(key)

        if key in manual_keys:
            row["classification"] = "skipped"
            row["attendance_status"] = "Skipped"
            row["skip_reason"] = "Manual attendance kept"
            continue

        shifts = schedules.get(key, [])
        approved_leave = any(
            start_date <= key[1] <= end_date
            for start_date, end_date in leave_spans.get(key[0], [])
        )
        has_punches = bool(row.get("actual_in") and row.get("actual_out"))
        if row["is_absent"] or not has_punches:
            if shifts and not approved_leave:
                row["classification"] = "review"
                row["attendance_status"] = "Needs Review"
                row["needs_review"] = 1
                row["is_absent"] = 1
                row["review_reason"] = "Absent on scheduled day"
            else:
                row["classification"] = "skipped"
                row["attendance_status"] = "Skipped"
                row["skip_reason"] = "Approved leave" if approved_leave else "No attendance recorded"
            continue

        if key in rest_days:
            row["classification"] = "review"
            row["attendance_status"] = "Needs Review"
            row["needs_review"] = 1
            row["review_reason"] = "Present on rest day"
            continue

        planned = scheduled_interval(shifts)
        actual = actual_interval(row)
        if planned and actual:
            start_delta = round((actual[0] - planned[0]).total_seconds() / 60)
            end_delta = round((actual[1] - planned[1]).total_seconds() / 60)
            if max(abs(start_delta), abs(end_delta)) > variance_minutes:
                row["classification"] = "review"
                row["attendance_status"] = "Needs Review"
                row["needs_review"] = 1
                row["review_reason"] = (
                    f"Major schedule variance: clock-in {start_delta:+d} min, "
                    f"clock-out {end_delta:+d} min"
                )
                continue

        row["classification"] = "approved"
        row["attendance_status"] = "Approved"

    return variance_minutes


@router.get("/attendance/template.csv")
def attendance_template_csv(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Response:
    require_attendance_importer(authorization, x_api_key)
    sample = [
        "2026-06-16",
        "Mary Grace Vito",
        "",
        "5:52 AM",
        "3:01 PM",
        "2026-06-16",
        "60",
        "ON-TIME",
        "",
        "0",
        "0",
        "0",
        "",
        "",
        "0",
        "",
    ]
    content = ",".join(TEMPLATE_COLUMNS) + "\n" + ",".join(sample) + "\n"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance-upload-template.csv"},
    )


@router.post("/attendance/template-import")
def import_attendance_template(
    payload: AttendanceTemplateImportPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_attendance_importer(authorization, x_api_key)
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No attendance rows were provided.")
    if len(payload.rows) > MAX_TEMPLATE_ROWS:
        raise HTTPException(status_code=400, detail=f"Attendance template cannot exceed {MAX_TEMPLATE_ROWS:,} rows.")

    conn = get_conn(DB_PATH)
    try:
        by_code, by_name = employee_lookup(conn)
        validated = [
            validate_template_row(row, by_code, by_name, index + 2)
            for index, row in enumerate(payload.rows)
        ]
        variance_minutes = apply_attendance_triage(conn, validated)
        success_rows = [row for row in validated if row["classification"] == "approved"]
        review_rows = [row for row in validated if row["classification"] == "review"]
        error_rows = [row for row in validated if row["classification"] == "error"]
        skipped_rows = [row for row in validated if row["classification"] == "skipped"]
        importable_rows = success_rows + review_rows
        summary = {
            "rows": len(validated),
            "ready": len(success_rows),
            "needs_review": len(review_rows),
            "errors": len(error_rows),
            "skipped": len(skipped_rows),
            "manual_preserved": sum(1 for row in skipped_rows if row["skip_reason"] == "Manual attendance kept"),
            "imported": 0 if payload.dry_run else len(importable_rows),
        }

        if not payload.dry_run:
            imported_at = now_iso()
            batch = conn.execute(
                """
                INSERT INTO data_import_batches(file_name, import_type, imported_at, imported_by, row_count, success_count, error_count, notes)
                VALUES (?, 'Attendance Template', ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean(payload.file_name) or "attendance-upload-template.csv",
                    imported_at,
                    user.get("display_name"),
                    len(validated),
                    len(importable_rows),
                    len(error_rows),
                    json.dumps(summary, sort_keys=True),
                ),
            )
            batch_id = int(batch.lastrowid)
            if payload.replace_template_rows:
                for row in validated:
                    if row.get("employee_id") and row.get("work_date") and row["classification"] != "error":
                        placeholders = ",".join("?" for _ in TEMPLATE_SOURCES)
                        conn.execute(
                            f"""
                            DELETE FROM time_logs
                            WHERE employee_id=? AND date(work_date)=date(?)
                              AND source IN ({placeholders})
                            """,
                            (row["employee_id"], row["work_date"], *TEMPLATE_SOURCES),
                        )
            for row in importable_rows:
                now = now_iso()
                needs_review = row["classification"] == "review"
                requested_ot = float(row["requested_ot_hours"] or 0)
                conn.execute(
                    """
                    INSERT INTO time_logs(
                        employee_id, work_date, actual_in, actual_out, source, verification_type,
                        device_employee_code, is_absent, absence_type, detected_ot_hours,
                        approved_ot_hours, ot_status, reviewed_by, reviewed_at,
                        attendance_status, review_reason, notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 'template_upload', 'Template Upload', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["employee_id"],
                        row["work_date"],
                        row["actual_in"],
                        row["actual_out"],
                        row["employee_code"],
                        row["is_absent"],
                        "Unconfirmed Absence" if row["is_absent"] else None,
                        requested_ot,
                        0 if needs_review else requested_ot,
                        "Pending" if needs_review and requested_ot else ("Approved" if requested_ot else "None"),
                        None if needs_review else user.get("display_name"),
                        None if needs_review else now,
                        row["attendance_status"],
                        row["review_reason"],
                        f"batch={batch_id} | {row['notes']}".strip(" |"),
                        now,
                        now,
                    ),
                )
            log_audit(
                conn,
                actor=user.get("display_name"),
                action="Attendance template imported",
                table_name="data_import_batches",
                record_id=batch_id,
                details=summary | {"variance_minutes": variance_minutes},
            )
            conn.commit()

        return {
            "ok": True,
            "dry_run": payload.dry_run,
            "summary": summary,
            "items": validated,
            "variance_minutes": variance_minutes,
            "mode": "attendance_template_preview" if payload.dry_run else "attendance_template_imported",
        }
    finally:
        conn.close()


@router.get("/attendance/imports")
def attendance_import_history(
    limit: int = Query(default=20, ge=1, le=100),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "supervisor"}:
        raise HTTPException(status_code=403, detail="Attendance history requires owner or General Manager access.")
    conn = get_conn(DB_PATH)
    try:
        rows = fetchall(
            conn,
            """
            SELECT id, file_name, imported_at, imported_by, row_count, notes
            FROM data_import_batches
            WHERE import_type='Attendance Template'
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        for row in rows:
            try:
                row["summary"] = json.loads(str(row.get("notes") or "{}"))
            except json.JSONDecodeError:
                row["summary"] = {}
            row.pop("notes", None)
        return {"ok": True, "items": rows}
    finally:
        conn.close()
