from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.attendance_template_import import (
    AttendanceTemplateImportPayload,
    clean,
    employee_lookup,
    require_attendance_importer,
    validate_template_row,
)
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import DB_PATH, fetchall, get_conn, now_iso

router = APIRouter(prefix="/api/v1")


def _link_split_shift_rows(conn, rows: list[dict[str, Any]]) -> None:
    """Attach import rows to exact scheduled shifts without guessing ambiguous cases.

    The biometric/template format has no shift-id column. For an employee-day with
    multiple scheduled shifts, a safe deterministic mapping exists when the upload
    contains exactly one timed attendance row per scheduled shift. In that case we
    pair rows and shifts in chronological start-time order. Otherwise rows remain
    unlinked and are forced to Needs Review rather than silently contaminating a
    different shift's payroll calculation.
    """

    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        employee_id = row.get("employee_id")
        work_date = row.get("work_date")
        if employee_id and work_date:
            groups[(int(employee_id), str(work_date))].append(row)

    for (employee_id, work_date), group_rows in groups.items():
        shifts = fetchall(
            conn,
            """
            SELECT id, start_time, end_time
            FROM scheduled_shifts
            WHERE employee_id=? AND date(shift_date)=date(?)
            ORDER BY start_time, id
            """,
            (employee_id, work_date),
        )

        for row in group_rows:
            row["scheduled_shift_id"] = None
            row["shift_match_mode"] = "unlinked"

        if not shifts:
            continue

        if len(shifts) == 1 and len(group_rows) == 1:
            group_rows[0]["scheduled_shift_id"] = int(shifts[0]["id"])
            group_rows[0]["shift_match_mode"] = "single_shift"
            continue

        timed_rows = [row for row in group_rows if row.get("actual_in")]
        distinct_times = {str(row.get("actual_in")) for row in timed_rows}
        if (
            len(shifts) == len(group_rows)
            and len(timed_rows) == len(group_rows)
            and len(distinct_times) == len(group_rows)
        ):
            ordered_rows = sorted(
                group_rows,
                key=lambda row: (str(row.get("actual_in")), int(row.get("row_number") or 0)),
            )
            for row, shift in zip(ordered_rows, shifts, strict=True):
                row["scheduled_shift_id"] = int(shift["id"])
                row["shift_match_mode"] = "ordered_split_shift"
            continue

        message = (
            f"Employee has {len(shifts)} scheduled shifts on {work_date}. "
            "Provide exactly one attendance row per shift with a distinct time_in so each log can be linked safely."
        )
        for row in group_rows:
            issues = list(row.get("issues") or [])
            if message not in issues:
                issues.append(message)
            row["issues"] = issues
            row["needs_review"] = 1
            row["attendance_status"] = "Needs Review"
            row["shift_match_mode"] = "ambiguous_split_shift"


@router.post("/attendance/template-import-v2")
def import_attendance_template_v2(
    payload: AttendanceTemplateImportPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_attendance_importer(authorization, x_api_key)
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No attendance rows were provided.")

    conn = get_conn(DB_PATH)
    try:
        ensure_schedule_schema(conn)
        by_code, by_name = employee_lookup(conn)
        validated = [
            validate_template_row(row, by_code, by_name, index + 2)
            for index, row in enumerate(payload.rows)
        ]
        importable_rows = [
            row for row in validated if row["employee_id"] and row["work_date"]
        ]

        _link_split_shift_rows(conn, importable_rows)

        success_rows = [
            row for row in validated if row["employee_id"] and row["work_date"] and not row["issues"]
        ]
        review_rows = [
            row for row in validated if row["employee_id"] and row["work_date"] and row["issues"]
        ]
        error_rows = [
            row for row in validated if not row["employee_id"] or not row["work_date"]
        ]

        if not payload.dry_run:
            imported_at = now_iso()
            batch = conn.execute(
                """
                INSERT INTO data_import_batches(
                    file_name, import_type, imported_at, imported_by,
                    row_count, success_count, error_count, notes
                )
                VALUES (?, 'Attendance Template', ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean(payload.file_name) or "attendance-upload-template.csv",
                    imported_at,
                    user.get("display_name"),
                    len(validated),
                    len(importable_rows),
                    len(error_rows),
                    "Attendance template upload with split-shift linkage.",
                ),
            )
            batch_id = int(batch.lastrowid)

            if payload.replace_template_rows:
                replacement_groups = {
                    (int(row["employee_id"]), str(row["work_date"]))
                    for row in importable_rows
                }
                for employee_id, work_date in sorted(replacement_groups):
                    conn.execute(
                        """
                        DELETE FROM time_logs
                        WHERE employee_id=?
                          AND work_date=?
                          AND source IN ('template_upload', 'attendance_template')
                        """,
                        (employee_id, work_date),
                    )

            for row in importable_rows:
                now = now_iso()
                needs_review = bool(row.get("needs_review") or row.get("issues"))
                notes = str(row.get("notes") or "")
                if row.get("shift_match_mode"):
                    notes = (
                        f"{notes} | " if notes else ""
                    ) + f"shift_match={row['shift_match_mode']}"
                conn.execute(
                    """
                    INSERT INTO time_logs(
                        scheduled_shift_id,
                        employee_id, work_date, actual_in, actual_out,
                        source, verification_type, device_employee_code,
                        is_absent, approved_ot_hours, ot_status,
                        reviewed_by, reviewed_at, attendance_status,
                        notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'template_upload', 'Template Upload', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("scheduled_shift_id"),
                        row["employee_id"],
                        row["work_date"],
                        row["actual_in"],
                        row["actual_out"],
                        row["employee_code"],
                        row["is_absent"],
                        row["approved_ot_hours"],
                        "Pending" if row["approved_ot_hours"] else "None",
                        None if needs_review else user.get("display_name"),
                        None if needs_review else now,
                        "Needs Review" if needs_review else row["attendance_status"],
                        f"batch={batch_id} | {notes}".strip(" |"),
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
                "shift_linked": sum(1 for row in importable_rows if row.get("scheduled_shift_id")),
            },
            "items": validated,
            "mode": "attendance_template_preview_v2" if payload.dry_run else "attendance_template_imported_v2",
        }
    finally:
        conn.close()
