from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user
from core.db import DB_PATH, get_conn, now_iso
from core.schedule_source import legacy_schedule_rows, table_exists

router = APIRouter(prefix="/api/v1")


class LegacyScheduleBackfillPayload(BaseModel):
    all: bool = False
    start: date | None = None
    end: date | None = None
    employee_id: int | None = None
    dry_run: bool = True


def legacy_bounds(conn) -> tuple[str, str] | None:
    if not table_exists(conn, "schedules"):
        return None
    row = conn.execute("SELECT MIN(work_date), MAX(work_date) FROM schedules WHERE COALESCE(is_rest_day,0)=0").fetchone()
    if not row or not row[0] or not row[1]:
        return None
    return str(row[0]), str(row[1])


def has_existing_log(conn, employee_id: int, work_date: str) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM time_logs
        WHERE employee_id=?
          AND work_date=?
          AND COALESCE(attendance_status, 'Pending') != 'Rejected'
        LIMIT 1
        """,
        (employee_id, work_date),
    ).fetchone()
    return bool(row)


@router.post("/schedules/legacy-backfill")
def legacy_schedule_backfill(
    payload: LegacyScheduleBackfillPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        bounds = legacy_bounds(conn)
        if not bounds:
            return {"ok": True, "dry_run": payload.dry_run, "inserted": 0, "would_insert": 0, "skipped": 0, "total_legacy_rows": 0, "sample": [], "message": "No legacy schedule rows found."}
        if payload.all:
            start, end = bounds
        else:
            if not payload.start or not payload.end:
                raise HTTPException(status_code=400, detail="Use all=true or provide start and end dates.")
            start, end = payload.start.isoformat(), payload.end.isoformat()
        if end < start:
            raise HTTPException(status_code=400, detail="End date cannot be before start date.")

        rows = [row for row in legacy_schedule_rows(conn, start, end, payload.employee_id) if not int(row.get("is_rest_day") or 0)]
        total = len(rows)
        skipped_existing = 0
        skipped_invalid = 0
        inserted = 0
        sample: list[dict[str, Any]] = []
        timestamp = now_iso()

        for row in rows:
            employee_id = int(row.get("employee_id") or 0)
            work_date = str(row.get("work_date") or "")
            shift_start = str(row.get("shift_start") or "")[:5]
            shift_end = str(row.get("shift_end") or "")[:5]
            if not employee_id or not work_date or not shift_start or not shift_end:
                skipped_invalid += 1
                continue
            if has_existing_log(conn, employee_id, work_date):
                skipped_existing += 1
                continue
            inserted += 1
            if len(sample) < 20:
                sample.append({"employee_id": employee_id, "work_date": work_date, "actual_in": shift_start, "actual_out": shift_end})
            if payload.dry_run:
                continue
            conn.execute(
                """
                INSERT INTO time_logs(
                    employee_id, work_date, actual_in, actual_out,
                    source, verification_type, is_absent,
                    detected_ot_hours, approved_ot_hours, ot_status,
                    attendance_status, notes, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    employee_id,
                    work_date,
                    shift_start,
                    shift_end,
                    "legacy_schedule",
                    "Legacy Schedule",
                    0,
                    0,
                    0,
                    "None",
                    "Approved",
                    "Backfilled from legacy schedule; scheduled time treated as actual time for old payroll data.",
                    timestamp,
                    timestamp,
                ),
            )
        if not payload.dry_run:
            conn.commit()
        return {
            "ok": True,
            "dry_run": payload.dry_run,
            "range_start": start,
            "range_end": end,
            "legacy_bounds_start": bounds[0],
            "legacy_bounds_end": bounds[1],
            "total_legacy_rows": total,
            "would_insert": inserted if payload.dry_run else 0,
            "inserted": 0 if payload.dry_run else inserted,
            "skipped_existing": skipped_existing,
            "skipped_invalid": skipped_invalid,
            "skipped": skipped_existing + skipped_invalid,
            "sample": sample,
            "message": "Preview complete." if payload.dry_run else "Legacy schedule backfill complete.",
        }
    finally:
        conn.close()
