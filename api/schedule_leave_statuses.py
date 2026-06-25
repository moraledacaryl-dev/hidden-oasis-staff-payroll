from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Header, Query

from api.schedule_day_reset import ResetDayPayload, reset_day
from api.schedules import require_schedule_viewer
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter(prefix="/api/v1")


@router.post("/schedules/day/reset")
def reset_schedule_day(
    payload: ResetDayPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    return reset_day(payload, authorization, x_api_key)


@router.get("/schedules/leave-statuses")
def leave_statuses(
    week_start: date = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    require_schedule_viewer(authorization, x_api_key)
    week_end = week_start + timedelta(days=6)
    conn = get_conn(DB_PATH)
    try:
        leave_rows = fetchall(
            conn,
            """
            SELECT lr.id, lr.employee_id, lr.start_date, lr.end_date,
                   COALESCE(lt.name, 'Leave') AS leave_type_name,
                   COALESCE(lr.paid, 0) AS paid,
                   COALESCE(lr.status, 'Approved') AS status,
                   COALESCE(lr.days, 1) AS days,
                   lr.reason
            FROM leave_requests lr
            LEFT JOIN leave_types lt ON lt.id=lr.leave_type_id
            WHERE date(lr.start_date) <= date(?)
              AND date(lr.end_date) >= date(?)
              AND lower(COALESCE(lr.status, 'approved')) NOT IN
                  ('rejected','declined','cancelled','canceled','void')
            ORDER BY lr.employee_id, lr.start_date, lr.id
            """,
            (week_end.isoformat(), week_start.isoformat()),
        )

        items = []
        occupied: set[tuple[int, str]] = set()

        for row in leave_rows:
            start = max(date.fromisoformat(str(row["start_date"])[:10]), week_start)
            end = min(date.fromisoformat(str(row["end_date"])[:10]), week_end)
            cursor = start
            while cursor <= end:
                work_date = cursor.isoformat()
                employee_id = int(row["employee_id"])
                items.append({**row, "work_date": work_date})
                occupied.add((employee_id, work_date))
                cursor += timedelta(days=1)

        absence_rows = fetchall(
            conn,
            """
            SELECT id, employee_id, work_date,
                   COALESCE(absence_type, 'Approved / Excused Absence') AS absence_type,
                   COALESCE(attendance_status, 'Approved') AS status,
                   notes
            FROM time_logs
            WHERE COALESCE(is_absent, 0)=1
              AND date(work_date) BETWEEN date(?) AND date(?)
            ORDER BY employee_id, work_date, id
            """,
            (week_start.isoformat(), week_end.isoformat()),
        )

        for row in absence_rows:
            employee_id = int(row["employee_id"])
            work_date = str(row["work_date"])[:10]
            key = (employee_id, work_date)
            if key in occupied:
                continue
            items.append(
                {
                    "id": -int(row["id"]),
                    "employee_id": employee_id,
                    "start_date": work_date,
                    "end_date": work_date,
                    "work_date": work_date,
                    "leave_type_name": row["absence_type"],
                    "paid": 0,
                    "status": row["status"],
                    "days": 1,
                    "reason": row["notes"],
                    "source": "absence_log",
                }
            )

        items.sort(key=lambda item: (int(item["employee_id"]), str(item["work_date"]), int(item["id"])))
        return {"ok": True, "items": items}
    finally:
        conn.close()
