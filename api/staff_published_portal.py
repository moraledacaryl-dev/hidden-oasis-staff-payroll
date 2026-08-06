from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api.cash_advance_service import ensure_schema as ensure_cash_schema, recalculate_balance
from api.hr_records import ensure_schema as ensure_hr_schema
from api.schedule_publication import ensure_schema as ensure_publication_schema
from api.security import current_user_from_token
from api.staff_schedule_ack import router as staff_schedule_ack_router
from api.staff_self_service import employee_for_user, my_self_service, require_staff_user
from core.audit import log_audit
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")
router.include_router(staff_schedule_ack_router)


class StaffLeaveRequestPayload(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str = Field(..., min_length=3, max_length=1000)


@router.get("/me/published-self-service")
def published_self_service(
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    data = my_self_service(user=user, x_api_key=x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_hr_schema(conn)
        ensure_publication_schema(conn)
        ensure_cash_schema(conn)
        employee = data.get("employee") or {}
        employee_id = int(employee.get("id") or 0)
        department = str(employee.get("department") or "").strip().lower()

        schedule = fetchall(
            conn,
            """
            SELECT s.source_shift_id AS id,
                   s.source_shift_id,
                   s.employee_id,
                   s.shift_date,
                   s.start_time,
                   s.end_time,
                   s.position,
                   s.department,
                   s.break_minutes,
                   s.status,
                   s.notes,
                   s.source,
                   s.week_start,
                   p.published_at,
                   p.published_by,
                   p.notes AS publication_notes
            FROM schedule_publication_shifts s
            JOIN schedule_publications p
              ON p.week_start=s.week_start AND p.status='Published'
            WHERE s.employee_id=?
            ORDER BY date(s.shift_date), s.start_time, s.id
            """,
            (employee_id,),
        ) if employee_id else []

        publication_rows = fetchall(
            conn,
            """
            SELECT DISTINCT p.week_start, p.published_at, p.published_by, p.notes
            FROM schedule_publications p
            JOIN schedule_publication_shifts s ON s.week_start=p.week_start
            WHERE p.status='Published' AND s.employee_id=?
            ORDER BY p.week_start
            """,
            (employee_id,),
        ) if employee_id else []

        publications: list[dict[str, Any]] = []
        for publication in publication_rows:
            ack = fetchone(
                conn,
                "SELECT acknowledged_at FROM schedule_acknowledgements WHERE week_start=? AND employee_id=?",
                (publication.get("week_start"), employee_id),
            )
            publications.append(
                {
                    **publication,
                    "acknowledged": bool(ack),
                    "acknowledged_at": ack.get("acknowledged_at") if ack else None,
                }
            )

        year = date.today().year
        leave = fetchall(
            conn,
            """SELECT lt.id AS leave_type_id, lt.name AS leave_type_name,
               COALESCE(ele.credits,0) AS credits, lt.paid,
               COALESCE((SELECT SUM(lr.days) FROM leave_requests lr
                 WHERE lr.employee_id=? AND lr.leave_type_id=lt.id
                   AND strftime('%Y',lr.start_date)=? AND lr.status IN ('Approved','Paid','Used')),0) AS used,
               COALESCE((SELECT SUM(lr.days) FROM leave_requests lr
                 WHERE lr.employee_id=? AND lr.leave_type_id=lt.id
                   AND strftime('%Y',lr.start_date)=? AND lr.status='Pending'),0) AS pending
               FROM leave_types lt
               LEFT JOIN employee_leave_entitlements ele
                 ON ele.leave_type_id=lt.id AND ele.employee_id=? AND ele.year=?
               WHERE lt.active=1
                 AND COALESCE(lt.staff_requestable,1)=1
                 AND (lt.paid=0 OR ele.entitled=1)
               ORDER BY lt.name""",
            (employee_id, str(year), employee_id, str(year), employee_id, year),
        ) if employee_id else []
        leave_balances = [
            {
                **row,
                "remaining": (
                    max(
                        0.0,
                        float(row.get("credits") or 0)
                        - float(row.get("used") or 0)
                        - float(row.get("pending") or 0),
                    )
                    if int(row.get("paid") or 0)
                    else None
                ),
            }
            for row in leave
        ]
        leave_requests = fetchall(
            conn,
            """
            SELECT lr.id, lr.start_date, lr.end_date, lr.days, lr.status, lr.reason,
                   lr.created_at, lr.decision_note, lt.name AS leave_type_name
            FROM leave_requests lr
            LEFT JOIN leave_types lt ON lt.id=lr.leave_type_id
            WHERE lr.employee_id=?
            ORDER BY date(lr.start_date) DESC, lr.id DESC
            LIMIT 100
            """,
            (employee_id,),
        ) if employee_id else []
        hr_records = fetchall(
            conn,
            """SELECT id,record_type,record_date,subject,details,severity,status,issued_by,acknowledged_at,resolved_at
               FROM hr_records WHERE employee_id=? AND status NOT IN ('Draft','Voided')
               ORDER BY date(record_date) DESC,id DESC LIMIT 100""",
            (employee_id,),
        ) if employee_id else []
        attendance = fetchall(
            conn,
            """
            SELECT work_date, actual_in, actual_out, attendance_status, is_absent,
                   absence_type, approved_ot_hours, notes
            FROM time_logs
            WHERE employee_id=?
            ORDER BY date(work_date) DESC, id DESC
            LIMIT 90
            """,
            (employee_id,),
        ) if employee_id else []
        cash_advances = fetchall(
            conn,
            """
            SELECT id, advance_date, amount, remaining_balance, status,
                   repayment_method, deduction_per_payroll
            FROM cash_advances
            WHERE employee_id=?
            ORDER BY date(advance_date) DESC, id DESC
            """,
            (employee_id,),
        ) if employee_id else []
        for advance in cash_advances:
            summary = recalculate_balance(conn, int(advance["id"]))
            advance["remaining_balance"] = summary["balance"]
            advance["status"] = summary["status"]
        coworker_shifts = fetchall(
            conn,
            """
            SELECT s.source_shift_id AS id, s.employee_id, e.full_name,
                   s.shift_date, s.start_time, s.end_time, s.position
            FROM schedule_publication_shifts s
            JOIN schedule_publications p
              ON p.week_start=s.week_start AND p.status='Published'
            JOIN employees e ON e.id=s.employee_id
            WHERE s.employee_id<>?
              AND lower(COALESCE(s.department,''))=?
              AND date(s.shift_date)>=date('now','localtime')
            ORDER BY date(s.shift_date), s.start_time, e.full_name
            """,
            (employee_id, department),
        ) if employee_id and department else []

        data["schedule"] = schedule
        data["publications"] = publications
        data["coworkers"] = [c for c in data.get("coworkers", []) if str(c.get("department") or "").strip().lower() == department]
        data["leave_balances"] = leave_balances
        data["leave_requests"] = leave_requests
        data["hr_records"] = hr_records
        data["attendance"] = attendance
        data["cash_advances"] = cash_advances
        data["coworker_shifts"] = coworker_shifts
        conn.commit()
        return data
    finally:
        conn.close()


@router.post("/me/leave-requests")
def submit_leave_request(
    payload: StaffLeaveRequestPayload,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="End date cannot be before start date.")
    if payload.end_date.year != payload.start_date.year:
        raise HTTPException(status_code=422, detail="Submit separate leave requests for each calendar year.")
    days = float((payload.end_date - payload.start_date).days + 1)
    conn = get_conn(DB_PATH)
    try:
        ensure_hr_schema(conn)
        employee = employee_for_user(conn, user)
        employee_id = int(employee["id"])
        leave_type = fetchone(
            conn,
            """
            SELECT * FROM leave_types
            WHERE id=? AND active=1 AND COALESCE(staff_requestable,1)=1
            """,
            (payload.leave_type_id,),
        )
        if not leave_type:
            raise HTTPException(status_code=404, detail="Leave type not found.")
        entitlement = fetchone(
            conn,
            """
            SELECT credits FROM employee_leave_entitlements
            WHERE employee_id=? AND leave_type_id=? AND year=? AND entitled=1
            """,
            (employee_id, payload.leave_type_id, payload.start_date.year),
        )
        if int(leave_type.get("paid") or 0):
            if not entitlement:
                raise HTTPException(status_code=422, detail="No active entitlement is set for this leave type.")
            used = fetchone(
                conn,
                """
                SELECT COALESCE(SUM(days),0) AS used FROM leave_requests
                WHERE employee_id=? AND leave_type_id=?
                  AND strftime('%Y',start_date)=?
                  AND status IN ('Pending','Approved','Paid','Used')
                """,
                (employee_id, payload.leave_type_id, str(payload.start_date.year)),
            ) or {}
            remaining = float(entitlement.get("credits") or 0) - float(used.get("used") or 0)
            if days > remaining:
                raise HTTPException(status_code=422, detail=f"Only {max(0, remaining):g} leave day(s) are available.")
        overlap = fetchone(
            conn,
            """
            SELECT id FROM leave_requests
            WHERE employee_id=? AND status IN ('Pending','Approved','Paid','Used')
              AND date(start_date)<=date(?) AND date(end_date)>=date(?)
            LIMIT 1
            """,
            (employee_id, payload.end_date.isoformat(), payload.start_date.isoformat()),
        )
        if overlap:
            raise HTTPException(status_code=409, detail="A leave request already overlaps these dates.")
        cursor = conn.execute(
            """
            INSERT INTO leave_requests(
                employee_id, leave_type_id, start_date, end_date, days,
                paid, status, reason, created_at
            ) VALUES(?,?,?,?,?,?,'Pending',?,?)
            """,
            (
                employee_id,
                payload.leave_type_id,
                payload.start_date.isoformat(),
                payload.end_date.isoformat(),
                days,
                int(leave_type.get("paid") or 0),
                payload.reason.strip(),
                datetime.now().replace(microsecond=0).isoformat(sep=" "),
            ),
        )
        request_id = int(cursor.lastrowid)
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="Leave request submitted",
            table_name="leave_requests",
            record_id=request_id,
            details={
                "employee_id": employee_id,
                "leave_type_id": payload.leave_type_id,
                "days": days,
            },
        )
        conn.commit()
        return {"ok": True, "request_id": request_id, "status": "Pending"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/me/leave-requests/{request_id}/withdraw")
def withdraw_leave_request(
    request_id: int,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    conn = get_conn(DB_PATH)
    try:
        ensure_hr_schema(conn)
        employee = employee_for_user(conn, user)
        row = fetchone(
            conn,
            "SELECT * FROM leave_requests WHERE id=? AND employee_id=?",
            (request_id, employee["id"]),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found.")
        if row.get("status") != "Pending":
            raise HTTPException(status_code=409, detail="Only pending leave requests can be withdrawn.")
        conn.execute(
            """
            UPDATE leave_requests
            SET status='Withdrawn', reviewed_by=?, reviewed_at=?, decision_note='Withdrawn by employee'
            WHERE id=?
            """,
            (
                user.get("display_name"),
                datetime.now().replace(microsecond=0).isoformat(sep=" "),
                request_id,
            ),
        )
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="Leave request withdrawn",
            table_name="leave_requests",
            record_id=request_id,
            details={"employee_id": employee["id"]},
        )
        conn.commit()
        return {"ok": True, "status": "Withdrawn"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
