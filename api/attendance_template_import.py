from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from api.main import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, get_conn, now_iso

router = APIRouter(prefix="/api/v1")

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
    if user.get("role_key") not in {"owner", "payroll", "supervisor"}:
        raise HTTPException(status_code=403, detail="Attendance import requires owner, payroll, or General Manager access.")
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
    if not is_absent and not actual_in and not actual_out:
        issues.append("Missing both time_in and time_out.")
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

    forced_review = truthy(row.needs_review)
    needs_review = forced_review or bool(issues) or truthy(row.is_halfday)

    status = clean(row.attendance_status) or clean(row.remarks) or ("Needs Review" if needs_review else "Approved")
    if needs_review and status.upper() in {"ON-TIME", "ON TIME", "GRACE PERIOD", "LATE"}:
        status = "Needs Review"

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
        "approved_ot_hours": ot_hours if truthy(row.is_ot) else 0.0,
        "attendance_status": status,
        "needs_review": 1 if needs_review else 0,
        "issues": issues,
        "notes": build_notes(row, time_out_date, work_date, issues),
    }


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

    conn = get_conn(DB_PATH)
    try:
        by_code, by_name = employee_lookup(conn)
        validated = [
            validate_template_row(row, by_code, by_name, index + 2)
            for index, row in enumerate(payload.rows)
        ]
        success_rows = [row for row in validated if row["employee_id"] and row["work_date"] and not row["issues"]]
        review_rows = [row for row in validated if row["employee_id"] and row["work_date"] and row["issues"]]
        error_rows = [row for row in validated if not row["employee_id"] or not row["work_date"]]
        importable_rows = [row for row in validated if row["employee_id"] and row["work_date"]]

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
                    "Clean attendance template upload.",
                ),
            )
            batch_id = int(batch.lastrowid)
            for row in importable_rows:
                if payload.replace_template_rows:
                    conn.execute(
                        """
                        DELETE FROM time_logs
                        WHERE employee_id=? AND work_date=? AND source IN ('template_upload', 'attendance_template')
                        """,
                        (row["employee_id"], row["work_date"]),
                    )
                now = now_iso()
                conn.execute(
                    """
                    INSERT INTO time_logs(
                        employee_id, work_date, actual_in, actual_out, source, verification_type,
                        device_employee_code, is_absent, approved_ot_hours, ot_status,
                        reviewed_by, reviewed_at, attendance_status, notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 'template_upload', 'Template Upload', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["employee_id"],
                        row["work_date"],
                        row["actual_in"],
                        row["actual_out"],
                        row["employee_code"],
                        row["is_absent"],
                        row["approved_ot_hours"],
                        "Pending" if row["approved_ot_hours"] else "None",
                        None if row["needs_review"] else user.get("display_name"),
                        None if row["needs_review"] else now,
                        "Needs Review" if row["needs_review"] else row["attendance_status"],
                        f"batch={batch_id} | {row['notes']}".strip(" |"),
                        now,
                        now,
                    ),
                )
            conn.commit()

        return {
            "ok": True,
            "dry_run": payload.dry_run,
            "summary": {
                "rows": len(validated),
                "ready": len(success_rows),
                "needs_review": len(review_rows),
                "errors": len(error_rows),
                "imported": 0 if payload.dry_run else len(importable_rows),
            },
            "items": validated,
            "mode": "attendance_template_preview" if payload.dry_run else "attendance_template_imported",
        }
    finally:
        conn.close()
