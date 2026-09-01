from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.schedules import DayActualPayload, DaySchedulePayload, MoveShiftPayload
from api.schedules import POSITIONS, clean_shift, day_bundle, employee_exists, require_schedule_editor
from api.schedules import ensure_schema, fetch_legacy_schedule_row, fetch_shift, fetch_time_log
from api.schedules import save_day_actual as canonical_save_day_actual
from api.schedule_change_log import ensure_schedule_change_log_schema, log_schedule_change
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter()


def row_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def local_now(conn) -> str:
    return str(conn.execute("SELECT datetime('now','localtime')").fetchone()[0])


def ensure_history_schema(conn) -> None:
    ensure_schema(conn)
    ensure_schedule_change_log_schema(conn)
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
    conn.commit()


def schedule_row(conn, shift_id: int) -> dict[str, Any] | None:
    return row_dict(fetchone(conn, "SELECT * FROM scheduled_shifts WHERE id=?", (shift_id,)))


def time_log_row(conn, log_id: int) -> dict[str, Any] | None:
    return row_dict(fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (log_id,)))


def migrate_legacy_row(conn, legacy_id: int, actor: str | None) -> int:
    existing = fetchone(conn, "SELECT id FROM scheduled_shifts WHERE legacy_schedule_id=?", (legacy_id,))
    if existing:
        return int(existing["id"])
    legacy = fetch_legacy_schedule_row(conn, legacy_id)
    if not legacy:
        raise HTTPException(status_code=404, detail="Legacy schedule row not found.")
    employee_id = int(legacy.get("employee_id") or 0)
    position = str(legacy.get("position") or "Other")
    if position not in POSITIONS:
        position = "Other"
    ts = local_now(conn)
    cur = conn.execute(
        """
        INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes, legacy_schedule_id, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, ?, 'planned', ?, ?)
        """,
        (employee_id, str(legacy.get("shift_date"))[:10], str(legacy.get("start_time"))[:5], str(legacy.get("end_time"))[:5], position, legacy.get("department") or legacy.get("employee_department"), int(legacy.get("break_minutes") or 0), legacy.get("notes"), legacy_id, ts, ts),
    )
    shift_id = int(cur.lastrowid)
    log_schedule_change(conn, change_type="migrate_legacy_schedule", entity_type="scheduled_shift", entity_id=shift_id, employee_id=employee_id, work_date=str(legacy.get("shift_date"))[:10], before=None, after=schedule_row(conn, shift_id), changed_by=actor)
    return shift_id


@router.post("/schedules/day/scheduled")
def save_schedule_history(payload: DaySchedulePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    employee_id = payload.employee_id if payload.employee_id and payload.employee_id > 0 else None
    conn = get_conn(DB_PATH)
    try:
        ensure_history_schema(conn)
        if employee_id and not employee_exists(conn, employee_id):
            raise HTTPException(status_code=404, detail="Employee not found.")
        if payload.position not in POSITIONS:
            raise HTTPException(status_code=422, detail="Invalid position.")
        shift_id = payload.shift_id
        if shift_id and shift_id < 0:
            shift_id = migrate_legacy_row(conn, abs(shift_id), user.get("display_name"))
        before = schedule_row(conn, shift_id) if shift_id else None
        ts = local_now(conn)
        if shift_id:
            if not before:
                raise HTTPException(status_code=404, detail="Shift not found.")
            conn.execute(
                """
                UPDATE scheduled_shifts SET employee_id=?, shift_date=?, start_time=?, end_time=?, position=?, department=?, break_minutes=?, notes=?, updated_at=? WHERE id=?
                """,
                (employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, int(payload.break_minutes or 0), payload.notes, ts, shift_id),
            )
            change_type = "update_schedule"
        else:
            cur = conn.execute(
                """
                INSERT INTO scheduled_shifts(employee_id, shift_date, start_time, end_time, position, department, break_minutes, status, notes, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, 'planned', ?, ?)
                """,
                (employee_id, payload.shift_date.isoformat(), payload.start_time, payload.end_time, payload.position, payload.department, int(payload.break_minutes or 0), payload.notes, ts, ts),
            )
            shift_id = int(cur.lastrowid)
            change_type = "create_schedule"
        after = schedule_row(conn, int(shift_id))
        log_schedule_change(conn, change_type=change_type, entity_type="scheduled_shift", entity_id=int(shift_id), employee_id=employee_id, work_date=payload.shift_date.isoformat(), before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return day_bundle(conn, payload.shift_date.isoformat(), employee_id, int(shift_id)) | {"message": "Scheduled shift saved. Existing payroll runs were not changed."}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/schedules/day/actual")
def save_actual_history(payload: DayActualPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    """Compatibility route: always use the canonical shift-aware actual writer.

    This legacy history route used to perform an employee/day lookup and could
    overwrite an unrelated unlinked biometric row on split-shift days. Keeping
    the route as a thin delegate makes route ordering harmless while historical
    consumers are phased out.
    """
    return canonical_save_day_actual(payload, authorization, x_api_key)


@router.post("/schedules/shifts/{shift_id}/move")
def move_shift_history(shift_id: int, payload: MoveShiftPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_history_schema(conn)
        if shift_id < 0:
            shift_id = migrate_legacy_row(conn, abs(shift_id), user.get("display_name"))
        before = schedule_row(conn, shift_id)
        if not before:
            raise HTTPException(status_code=404, detail="Shift not found.")
        conn.execute("UPDATE scheduled_shifts SET shift_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (payload.shift_date.isoformat(), shift_id))
        after = schedule_row(conn, shift_id)
        log_schedule_change(conn, change_type="move_schedule", entity_type="scheduled_shift", entity_id=shift_id, employee_id=int((after or {}).get("employee_id") or 0), work_date=payload.shift_date.isoformat(), before=before, after=after, changed_by=user.get("display_name"))
        conn.commit()
        return {"ok": True, "shift": clean_shift(after or {}), "mode": "historical_shift_moved_payroll_snapshot_unchanged"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()

@router.post("/schedules/shifts/{shift_id}/delete")
def delete_shift_history(
    shift_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_schedule_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_history_schema(conn)

        if shift_id < 0:
            legacy_id = abs(shift_id)
            legacy = fetch_legacy_schedule_row(conn, legacy_id)
            if not legacy:
                raise HTTPException(status_code=404, detail="Legacy schedule row not found.")

            conn.execute(
                """
                INSERT OR REPLACE INTO legacy_schedule_ignores(
                    legacy_schedule_id, ignored_by, ignored_at, reason
                ) VALUES (?, ?, ?, ?)
                """,
                (legacy_id, user.get("display_name"), local_now(conn), "Deleted from schedule page"),
            )

            log_schedule_change(
                conn,
                change_type="delete_legacy_schedule",
                entity_type="legacy_schedule",
                entity_id=legacy_id,
                employee_id=int(legacy.get("employee_id") or 0),
                work_date=str(legacy.get("shift_date"))[:10],
                before=legacy,
                after=None,
                changed_by=user.get("display_name"),
            )
            conn.commit()
            return {
                "ok": True,
                "deleted_shift_id": shift_id,
                "mode": "legacy_shift_hidden_payroll_snapshot_unchanged",
            }

        before = schedule_row(conn, shift_id)
        if not before:
            raise HTTPException(status_code=404, detail="Shift not found.")

        conn.execute("DELETE FROM scheduled_shifts WHERE id=?", (shift_id,))

        log_schedule_change(
            conn,
            change_type="delete_schedule",
            entity_type="scheduled_shift",
            entity_id=shift_id,
            employee_id=int(before.get("employee_id") or 0),
            work_date=str(before.get("shift_date"))[:10],
            before=before,
            after=None,
            changed_by=user.get("display_name"),
        )
        conn.commit()
        return {
            "ok": True,
            "deleted_shift_id": shift_id,
            "mode": "historical_shift_deleted_payroll_snapshot_unchanged",
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
