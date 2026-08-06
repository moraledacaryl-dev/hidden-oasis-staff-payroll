from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.security import current_user_from_token, require_api_key
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class AnnualReviewPayload(BaseModel):
    id: int | None = None
    employee_id: int
    review_year: int
    attendance_rating: int | None = None
    work_quality_rating: int | None = None
    reliability_rating: int | None = None
    teamwork_rating: int | None = None
    customer_service_rating: int | None = None
    initiative_rating: int | None = None
    sop_rating: int | None = None
    communication_rating: int | None = None
    overall_rating: int | None = None
    strengths: str | None = None
    improvements: str | None = None
    notable_events: str | None = None
    training_needed: str | None = None
    supervisor_recommendation: str | None = None
    final_result: str = "Draft"
    status: str = "Draft"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def require_review_user(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") not in {"owner", "supervisor"}:
        raise HTTPException(status_code=403, detail="Performance reviews require owner or General Manager access.")
    return user


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS annual_performance_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            review_year INTEGER NOT NULL,
            attendance_rating INTEGER,
            work_quality_rating INTEGER,
            reliability_rating INTEGER,
            teamwork_rating INTEGER,
            customer_service_rating INTEGER,
            initiative_rating INTEGER,
            sop_rating INTEGER,
            communication_rating INTEGER,
            overall_rating INTEGER,
            strengths TEXT,
            improvements TEXT,
            notable_events TEXT,
            training_needed TEXT,
            supervisor_recommendation TEXT,
            final_result TEXT DEFAULT 'Draft',
            status TEXT DEFAULT 'Draft',
            reviewer_name TEXT,
            reviewed_at TEXT,
            finalized_by TEXT,
            finalized_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id, review_year)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_annual_reviews_employee_year ON annual_performance_reviews(employee_id, review_year)")
    conn.commit()


def employee_select_sql(conn) -> str:
    cols = table_columns(conn, "employees")
    name_col = "full_name" if "full_name" in cols else "name"
    code_expr = "employee_code" if "employee_code" in cols else "'' AS employee_code"
    dept_expr = "department" if "department" in cols else "'' AS department"
    pos_expr = "position" if "position" in cols else "'' AS position"
    status_where = "WHERE COALESCE(employment_status, 'active') NOT IN ('inactive', 'terminated', 'resigned')" if "employment_status" in cols else ""
    return f"""
        SELECT id, {code_expr}, {name_col} AS full_name, {dept_expr}, {pos_expr}
        FROM employees
        {status_where}
        ORDER BY COALESCE(department, ''), {name_col}
    """


def previous_reviews(conn, employee_id: int, review_year: int) -> list[dict[str, Any]]:
    return fetchall(
        conn,
        """
        SELECT
            id,
            review_year,
            overall_rating,
            final_result,
            status,
            strengths,
            improvements,
            notable_events,
            training_needed,
            supervisor_recommendation,
            reviewer_name,
            reviewed_at,
            finalized_by,
            finalized_at
        FROM annual_performance_reviews
        WHERE employee_id=?
          AND review_year < ?
        ORDER BY review_year DESC
        LIMIT 3
        """,
        (employee_id, review_year),
    )


@router.get("/performance/annual-reviews")
def list_annual_reviews(
    year: int = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_review_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        if not table_exists(conn, "employees"):
            return {"ok": True, "year": year, "items": []}

        employees = fetchall(conn, employee_select_sql(conn))
        reviews = fetchall(
            conn,
            """
            SELECT *
            FROM annual_performance_reviews
            WHERE review_year=?
            """,
            (year,),
        )
        review_by_employee = {int(row["employee_id"]): row for row in reviews}

        items = []
        for employee in employees:
            employee_id = int(employee["id"])
            current = review_by_employee.get(employee_id)
            items.append({
                "employee": employee,
                "review": current,
                "previous_reviews": previous_reviews(conn, employee_id, year),
            })

        return {"ok": True, "year": year, "items": items}
    finally:
        conn.close()


@router.post("/performance/annual-reviews")
def save_annual_review(
    payload: AnnualReviewPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_review_user(authorization, x_api_key)
    role = user.get("role_key")
    timestamp = now_iso()

    if payload.status not in {"Draft", "Submitted", "Finalized"}:
        raise HTTPException(status_code=422, detail="Invalid annual review status.")

    if payload.status == "Finalized" and role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can finalize annual reviews.")

    ratings = [
        payload.attendance_rating,
        payload.work_quality_rating,
        payload.reliability_rating,
        payload.teamwork_rating,
        payload.customer_service_rating,
        payload.initiative_rating,
        payload.sop_rating,
        payload.communication_rating,
        payload.overall_rating,
    ]
    for rating in ratings:
        if rating is not None and (rating < 1 or rating > 5):
            raise HTTPException(status_code=422, detail="Ratings must be from 1 to 5.")

    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,))
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found.")

        existing = fetchone(
            conn,
            "SELECT * FROM annual_performance_reviews WHERE employee_id=? AND review_year=?",
            (payload.employee_id, payload.review_year),
        )

        final_result = payload.final_result or "Draft"
        if final_result not in {"Draft", "Excellent", "Good", "Satisfactory", "Needs Improvement", "Unsatisfactory"}:
            raise HTTPException(status_code=422, detail="Invalid final result.")

        finalized_by = user.get("display_name") if payload.status == "Finalized" else (existing.get("finalized_by") if existing else None)
        finalized_at = timestamp if payload.status == "Finalized" else (existing.get("finalized_at") if existing else None)

        values = (
            payload.attendance_rating,
            payload.work_quality_rating,
            payload.reliability_rating,
            payload.teamwork_rating,
            payload.customer_service_rating,
            payload.initiative_rating,
            payload.sop_rating,
            payload.communication_rating,
            payload.overall_rating,
            payload.strengths,
            payload.improvements,
            payload.notable_events,
            payload.training_needed,
            payload.supervisor_recommendation,
            final_result,
            payload.status,
            user.get("display_name"),
            timestamp,
            finalized_by,
            finalized_at,
            timestamp,
        )

        if existing:
            conn.execute(
                """
                UPDATE annual_performance_reviews
                SET
                    attendance_rating=?,
                    work_quality_rating=?,
                    reliability_rating=?,
                    teamwork_rating=?,
                    customer_service_rating=?,
                    initiative_rating=?,
                    sop_rating=?,
                    communication_rating=?,
                    overall_rating=?,
                    strengths=?,
                    improvements=?,
                    notable_events=?,
                    training_needed=?,
                    supervisor_recommendation=?,
                    final_result=?,
                    status=?,
                    reviewer_name=?,
                    reviewed_at=?,
                    finalized_by=?,
                    finalized_at=?,
                    updated_at=?
                WHERE id=?
                """,
                values + (int(existing["id"]),),
            )
            review_id = int(existing["id"])
        else:
            conn.execute(
                """
                INSERT INTO annual_performance_reviews (
                    employee_id,
                    review_year,
                    attendance_rating,
                    work_quality_rating,
                    reliability_rating,
                    teamwork_rating,
                    customer_service_rating,
                    initiative_rating,
                    sop_rating,
                    communication_rating,
                    overall_rating,
                    strengths,
                    improvements,
                    notable_events,
                    training_needed,
                    supervisor_recommendation,
                    final_result,
                    status,
                    reviewer_name,
                    reviewed_at,
                    finalized_by,
                    finalized_at,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (payload.employee_id, payload.review_year) + values + (timestamp,),
            )
            review_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        conn.commit()
        review = fetchone(conn, "SELECT * FROM annual_performance_reviews WHERE id=?", (review_id,))
        return {"ok": True, "review": review}
    finally:
        conn.close()

class PerformanceLogPayload(BaseModel):
    id: int | None = None
    employee_id: int
    log_date: str
    category: str = "Neutral"
    area: str = "General"
    severity: str = "Low"
    note: str
    private_note: str | None = None
    evidence_ref: str | None = None
    is_general: int = 0


def ensure_performance_logs_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Neutral',
            area TEXT NOT NULL DEFAULT 'General',
            severity TEXT NOT NULL DEFAULT 'Low',
            note TEXT NOT NULL,
            private_note TEXT,
            evidence_ref TEXT,
            is_general INTEGER DEFAULT 0,
            created_by TEXT,
            created_by_role TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_performance_logs_employee_date ON performance_logs(employee_id, log_date)")
    conn.commit()


@router.get("/performance/logs")
def list_performance_logs(
    employee_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_review_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_performance_logs_schema(conn)
        where = []
        params: list[Any] = []

        if employee_id is not None:
            where.append("pl.employee_id=?")
            params.append(employee_id)

        if year is not None:
            where.append("date(pl.log_date) BETWEEN date(?) AND date(?)")
            params.extend([f"{year}-01-01", f"{year}-12-31"])

        where_sql = "WHERE " + " AND ".join(where) if where else ""

        rows = fetchall(
            conn,
            f"""
            SELECT
                pl.*,
                e.full_name,
                e.employee_code,
                e.department,
                e.position
            FROM performance_logs pl
            LEFT JOIN employees e ON e.id = pl.employee_id
            {where_sql}
            ORDER BY date(pl.log_date) DESC, pl.id DESC
            """,
            tuple(params),
        )
        return {"ok": True, "items": rows}
    finally:
        conn.close()


@router.post("/performance/logs")
def save_performance_log(
    payload: PerformanceLogPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_review_user(authorization, x_api_key)
    timestamp = now_iso()

    if payload.category not in {"Positive", "Concern", "Neutral", "General"}:
        raise HTTPException(status_code=422, detail="Invalid log category.")
    if payload.severity not in {"Low", "Medium", "High"}:
        raise HTTPException(status_code=422, detail="Invalid severity.")
    if not payload.note.strip():
        raise HTTPException(status_code=422, detail="Note is required.")

    conn = get_conn(DB_PATH)
    try:
        ensure_performance_logs_schema(conn)

        if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
            raise HTTPException(status_code=404, detail="Employee not found.")

        existing = None
        if payload.id:
            existing = fetchone(conn, "SELECT * FROM performance_logs WHERE id=?", (payload.id,))
            if not existing:
                raise HTTPException(status_code=404, detail="Performance log not found.")
            if user.get("role_key") != "owner" and existing.get("created_by") != user.get("display_name"):
                raise HTTPException(status_code=403, detail="The General Manager can only edit their own performance logs.")

        values = (
            payload.employee_id,
            payload.log_date,
            payload.category,
            payload.area,
            payload.severity,
            payload.note.strip(),
            payload.private_note,
            payload.evidence_ref,
            int(payload.is_general or 0),
            user.get("display_name"),
            user.get("role_key"),
            timestamp,
        )

        if existing:
            conn.execute(
                """
                UPDATE performance_logs
                SET
                    employee_id=?,
                    log_date=?,
                    category=?,
                    area=?,
                    severity=?,
                    note=?,
                    private_note=?,
                    evidence_ref=?,
                    is_general=?,
                    created_by=?,
                    created_by_role=?,
                    updated_at=?
                WHERE id=?
                """,
                values + (payload.id,),
            )
            log_id = int(payload.id)
        else:
            conn.execute(
                """
                INSERT INTO performance_logs (
                    employee_id,
                    log_date,
                    category,
                    area,
                    severity,
                    note,
                    private_note,
                    evidence_ref,
                    is_general,
                    created_by,
                    created_by_role,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values + (timestamp,),
            )
            log_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        conn.commit()
        item = fetchone(conn, "SELECT * FROM performance_logs WHERE id=?", (log_id,))
        return {"ok": True, "item": item}
    finally:
        conn.close()
