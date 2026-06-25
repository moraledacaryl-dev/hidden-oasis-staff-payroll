from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header

from api.hr_records import ensure_schema as ensure_hr_schema
from api.main import current_user_from_token
from api.schedule_publication import publication_for_date, week_start_for_date
from api.staff_schedule_ack import router as staff_schedule_ack_router
from api.staff_self_service import my_self_service
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")
router.include_router(staff_schedule_ack_router)


@router.get("/me/published-self-service")
def published_self_service(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    data = my_self_service(user=user, x_api_key=x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_hr_schema(conn)
        employee = data.get("employee") or {}
        employee_id = int(employee.get("id") or 0)
        department = str(employee.get("department") or "").strip().lower()
        schedule: list[dict[str, Any]] = []
        publications: dict[str, dict[str, Any]] = {}

        for shift in data.get("schedule", []):
            publication = publication_for_date(conn, str(shift.get("shift_date")))
            if not publication:
                continue
            week_start = week_start_for_date(str(shift.get("shift_date")))
            ack = fetchone(
                conn,
                "SELECT acknowledged_at FROM schedule_acknowledgements WHERE week_start=? AND employee_id=?",
                (week_start, employee_id),
            ) if employee_id else None
            publications[week_start] = {
                "week_start": week_start,
                "published_at": publication.get("published_at"),
                "published_by": publication.get("published_by"),
                "notes": publication.get("notes"),
                "acknowledged": bool(ack),
                "acknowledged_at": ack.get("acknowledged_at") if ack else None,
            }
            schedule.append({**shift, "week_start": week_start})

        year = date.today().year
        leave = fetchall(
            conn,
            """SELECT lt.name AS leave_type_name, ele.credits, lt.paid,
               COALESCE((SELECT SUM(lr.days) FROM leave_requests lr
                 WHERE lr.employee_id=ele.employee_id AND lr.leave_type_id=ele.leave_type_id
                   AND strftime('%Y',lr.start_date)=? AND lr.status IN ('Approved','Paid','Used')),0) AS used
               FROM employee_leave_entitlements ele JOIN leave_types lt ON lt.id=ele.leave_type_id
               WHERE ele.employee_id=? AND ele.year=? AND ele.entitled=1 AND lt.active=1 ORDER BY lt.name""",
            (str(year), employee_id, year),
        ) if employee_id else []
        leave_balances = [{**row, "remaining": max(0.0, float(row.get("credits") or 0)-float(row.get("used") or 0))} for row in leave]
        hr_records = fetchall(
            conn,
            """SELECT id,record_type,record_date,subject,details,severity,status,issued_by,acknowledged_at,resolved_at
               FROM hr_records WHERE employee_id=? AND status NOT IN ('Draft','Voided')
               ORDER BY date(record_date) DESC,id DESC LIMIT 100""",
            (employee_id,),
        ) if employee_id else []

        data["schedule"] = schedule
        data["publications"] = list(publications.values())
        data["coworkers"] = [c for c in data.get("coworkers", []) if str(c.get("department") or "").strip().lower() == department]
        data["leave_balances"] = leave_balances
        data["hr_records"] = hr_records
        return data
    finally:
        conn.close()
