from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
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


def _clock_datetime(day: str, clock: str, *, next_day_if_needed_from: datetime | None = None) -> datetime:
    value = datetime.fromisoformat(f"{day}T{clock}")
    if next_day_if_needed_from is not None and value <= next_day_if_needed_from:
        value += timedelta(days=1)
    return value


def _shift_interval(work_date: str, shift: dict[str, Any]) -> tuple[datetime, datetime]:
    start = _clock_datetime(work_date, str(shift["start_time"]))
    end = _clock_datetime(work_date, str(shift["end_time"]), next_day_if_needed_from=start)
    return start, end


def _actual_interval(row: dict[str, Any]) -> tuple[datetime, datetime] | None:
    actual_in = str(row.get("actual_in") or "").strip()
    actual_out = str(row.get("actual_out") or "").strip()
    work_date = str(row.get("work_date") or "").strip()
    if not actual_in or not actual_out or not work_date:
        return None

    start = _clock_datetime(work_date, actual_in)
    out_date = str(row.get("time_out_date") or work_date).strip() or work_date
    end = _clock_datetime(out_date, actual_out)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _segment_continuous_row_across_shifts(
    row: dict[str, Any],
    shifts: list[dict[str, Any]],
    work_date: str,
) -> list[dict[str, Any]] | None:
    """Split one continuous biometric span across touching scheduled shifts.

    This is intentionally conservative. We segment only when every scheduled shift
    touches the next shift exactly and the uploaded actual interval crosses every
    internal boundary. That proves the single biometric interval covers the whole
    split-duty chain without inventing attendance inside an unscheduled gap.
    """

    interval = _actual_interval(row)
    if interval is None or len(shifts) < 2:
        return None
    actual_start, actual_end = interval

    shift_intervals = [_shift_interval(work_date, shift) for shift in shifts]
    for index in range(len(shift_intervals) - 1):
        if shift_intervals[index][1] != shift_intervals[index + 1][0]:
            return None

    boundaries = [shift_intervals[index][1] for index in range(len(shift_intervals) - 1)]
    if any(not (actual_start < boundary < actual_end) for boundary in boundaries):
        return None

    # The outer biometric interval must overlap the first and last scheduled shifts.
    if actual_start >= shift_intervals[0][1] or actual_end <= shift_intervals[-1][0]:
        return None

    segments: list[dict[str, Any]] = []
    for index, shift in enumerate(shifts):
        segment = dict(row)
        segment_start = actual_start if index == 0 else shift_intervals[index][0]
        segment_end = actual_end if index == len(shifts) - 1 else shift_intervals[index][1]
        segment["actual_in"] = segment_start.strftime("%H:%M")
        segment["actual_out"] = segment_end.strftime("%H:%M")
        segment["scheduled_shift_id"] = int(shift["id"])
        segment["shift_match_mode"] = "continuous_split_segmented"
        segment["segment_index"] = index + 1
        segment["segment_count"] = len(shifts)
        notes = str(segment.get("notes") or "").strip()
        marker = (
            f"continuous biometric span segmented {index + 1}/{len(shifts)} "
            f"for shift_id={int(shift['id'])}"
        )
        segment["notes"] = f"{notes} | {marker}".strip(" |")
        segments.append(segment)

    row["scheduled_shift_id"] = None
    row["shift_match_mode"] = "continuous_split_segmented"
    row["segments_generated"] = len(segments)
    return segments


def _link_split_shift_rows(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach import rows to exact scheduled shifts without unsafe guessing.

    Supported deterministic shapes are:
    1. one attendance row for one scheduled shift;
    2. one distinct attendance row per same-day shift, paired chronologically;
    3. one continuous biometric interval spanning multiple *touching* shifts,
       segmented at the scheduled internal boundaries.
    """

    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        employee_id = row.get("employee_id")
        work_date = row.get("work_date")
        if employee_id and work_date:
            groups[(int(employee_id), str(work_date))].append(row)

    output_rows: list[dict[str, Any]] = []

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
            output_rows.extend(group_rows)
            continue

        if len(shifts) == 1 and len(group_rows) == 1:
            group_rows[0]["scheduled_shift_id"] = int(shifts[0]["id"])
            group_rows[0]["shift_match_mode"] = "single_shift"
            output_rows.extend(group_rows)
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
            output_rows.extend(group_rows)
            continue

        if len(group_rows) == 1:
            segmented = _segment_continuous_row_across_shifts(group_rows[0], shifts, work_date)
            if segmented:
                output_rows.extend(segmented)
                continue

        message = (
            f"Employee has {len(shifts)} scheduled shifts on {work_date}. "
            "Provide one row per shift, or one continuous biometric interval that crosses every boundary between contiguous shifts."
        )
        for row in group_rows:
            issues = list(row.get("issues") or [])
            if message not in issues:
                issues.append(message)
            row["issues"] = issues
            row["needs_review"] = 1
            row["attendance_status"] = "Needs Review"
            row["shift_match_mode"] = "ambiguous_split_shift"
        output_rows.extend(group_rows)

    return output_rows


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
        source_importable_rows = [
            row for row in validated if row["employee_id"] and row["work_date"]
        ]

        importable_rows = _link_split_shift_rows(conn, source_importable_rows)

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
                    "Attendance template upload with exact split-shift linkage and continuous-span segmentation.",
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
                "segments_generated": sum(1 for row in importable_rows if row.get("shift_match_mode") == "continuous_split_segmented"),
            },
            "items": validated,
            "mode": "attendance_template_preview_v2" if payload.dry_run else "attendance_template_imported_v2",
        }
    finally:
        conn.close()
