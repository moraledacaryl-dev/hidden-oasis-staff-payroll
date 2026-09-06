from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Query

from api.performance_reviews import (
    employee_select_sql,
    previous_reviews,
    require_review_user,
    router as legacy_router,
    table_exists,
)
from core.db import DB_PATH, fetchall, get_conn

router = APIRouter()

# Preserve the existing write handlers unchanged. Read handlers are redefined
# below so schema creation/commit remains a startup responsibility.
for route in legacy_router.routes:
    methods = {str(method).upper() for method in getattr(route, "methods", set())}
    if "GET" not in methods:
        router.routes.append(route)


@router.get("/api/v1/performance/annual-reviews")
def list_annual_reviews_readonly(
    year: int = Query(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_review_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
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
            items.append(
                {
                    "employee": employee,
                    "review": review_by_employee.get(employee_id),
                    "previous_reviews": previous_reviews(conn, employee_id, year),
                }
            )

        return {"ok": True, "year": year, "items": items}
    finally:
        conn.close()


@router.get("/api/v1/performance/logs")
def list_performance_logs_readonly(
    employee_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_review_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        where: list[str] = []
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
