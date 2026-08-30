from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.main import configured_db_path
from api.security import require_api_key, require_roles
from core.audit import log_audit
from core.db import fetchall, fetchone, get_conn, now_iso

router = APIRouter(prefix="/api/v1/holidays", dependencies=[Depends(require_api_key)])

HolidayType = Literal["Regular Holiday", "Special Non-Working Day"]


class HolidayPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    holiday_date: date
    name: str = Field(..., min_length=1, max_length=160)
    holiday_type: HolidayType
    active: bool = True
    notes: str | None = Field(default=None, max_length=500)


def _row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "holiday_date": str(row["holiday_date"]),
        "name": str(row["name"]),
        "holiday_type": str(row["holiday_type"]),
        "active": bool(row["active"]),
        "notes": row.get("notes"),
        "created_at": row.get("created_at"),
    }


@router.get("")
def list_holidays(
    user: dict[str, Any] = Depends(require_roles("owner", "payroll")),
) -> dict[str, Any]:
    conn = get_conn(configured_db_path())
    try:
        rows = fetchall(conn, "SELECT * FROM holidays ORDER BY holiday_date DESC, id DESC")
        return {"ok": True, "items": [_row(row) for row in rows]}
    finally:
        conn.close()


def _save(payload: HolidayPayload, holiday_id: int | None, user: dict[str, Any]) -> dict[str, Any]:
    conn = get_conn(configured_db_path())
    try:
        duplicate = fetchone(
            conn,
            "SELECT id FROM holidays WHERE holiday_date=? AND (? IS NULL OR id<>?)",
            (payload.holiday_date.isoformat(), holiday_id, holiday_id),
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="A holiday is already configured for this date.")
        if holiday_id is None:
            cursor = conn.execute(
                "INSERT INTO holidays(holiday_date,name,holiday_type,active,notes,created_at) VALUES(?,?,?,?,?,?)",
                (payload.holiday_date.isoformat(), payload.name, payload.holiday_type, int(payload.active), payload.notes, now_iso()),
            )
            holiday_id = int(cursor.lastrowid)
            action = "Holiday created"
        else:
            existing = fetchone(conn, "SELECT id FROM holidays WHERE id=?", (holiday_id,))
            if not existing:
                raise HTTPException(status_code=404, detail="Holiday not found.")
            conn.execute(
                "UPDATE holidays SET holiday_date=?, name=?, holiday_type=?, active=?, notes=? WHERE id=?",
                (payload.holiday_date.isoformat(), payload.name, payload.holiday_type, int(payload.active), payload.notes, holiday_id),
            )
            action = "Holiday updated"
        log_audit(conn, actor=user.get("display_name"), action=action, table_name="holidays", record_id=holiday_id, details={"holiday_date": payload.holiday_date.isoformat(), "holiday_type": payload.holiday_type, "active": payload.active})
        conn.commit()
        row = fetchone(conn, "SELECT * FROM holidays WHERE id=?", (holiday_id,))
        return {"ok": True, "item": _row(row or {})}
    finally:
        conn.close()


@router.post("")
def create_holiday(payload: HolidayPayload, user: dict[str, Any] = Depends(require_roles("owner", "payroll"))) -> dict[str, Any]:
    return _save(payload, None, user)


@router.put("/{holiday_id}")
def update_holiday(holiday_id: int, payload: HolidayPayload, user: dict[str, Any] = Depends(require_roles("owner", "payroll"))) -> dict[str, Any]:
    return _save(payload, holiday_id, user)
