from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import configured_db_path, require_api_key, require_roles
from core.db import fetchall, fetchone, get_conn, now_iso
from core.integration_outbox import DESTINATION_ENV, ensure_integration_schema, process_due_events

router = APIRouter(prefix="/api/v1/integrations", dependencies=[Depends(require_api_key)])


def _summary(conn) -> dict[str, Any]:
    rows = fetchall(
        conn,
        "SELECT destination,status,COUNT(*) AS count FROM integration_outbox GROUP BY destination,status ORDER BY destination,status",
    )
    destinations: dict[str, dict[str, Any]] = {}
    for destination in DESTINATION_ENV:
        destinations[destination] = {
            "configured": bool(__import__("os").getenv(DESTINATION_ENV[destination][0], "").strip()),
            "statuses": {},
        }
    for row in rows:
        destinations.setdefault(row["destination"], {"configured": False, "statuses": {}})
        destinations[row["destination"]]["statuses"][row["status"]] = int(row["count"])
    return {"destinations": destinations}


@router.get("/status")
def integration_status(
    user: dict[str, Any] = Depends(require_roles("owner", "payroll")),
) -> dict[str, Any]:
    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        latest = fetchall(
            conn,
            """
            SELECT id,destination,event_type,external_id,status,attempt_count,max_attempts,
                   next_attempt_at,last_attempt_at,last_error,completed_at,dead_letter_at,created_at
            FROM integration_outbox ORDER BY id DESC LIMIT 50
            """,
        )
        return {**_summary(conn), "latest": latest}
    finally:
        conn.close()


@router.get("/events")
def list_events(
    destination: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict[str, Any] = Depends(require_roles("owner", "payroll")),
) -> list[dict[str, Any]]:
    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        clauses: list[str] = []
        params: list[Any] = []
        if destination:
            clauses.append("destination=?")
            params.append(destination)
        if status:
            clauses.append("status=?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return fetchall(
            conn,
            f"""
            SELECT id,destination,event_type,external_source,external_id,source_type,source_id,
                   status,attempt_count,max_attempts,next_attempt_at,last_attempt_at,last_error,
                   completed_at,dead_letter_at,created_at,updated_at
            FROM integration_outbox {where} ORDER BY id DESC LIMIT ?
            """,
            (*params, int(limit)),
        )
    finally:
        conn.close()


@router.get("/events/{event_id}")
def event_detail(
    event_id: int,
    user: dict[str, Any] = Depends(require_roles("owner", "payroll")),
) -> dict[str, Any]:
    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        row = fetchone(conn, "SELECT * FROM integration_outbox WHERE id=?", (event_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Integration event not found.")
        row["payload"] = json.loads(row.pop("payload_json") or "{}")
        row["response"] = json.loads(row.pop("response_json") or "{}") if row.get("response_json") else None
        return row
    finally:
        conn.close()


@router.post("/events/{event_id}/retry")
def retry_event(
    event_id: int,
    user: dict[str, Any] = Depends(require_roles("owner")),
) -> dict[str, Any]:
    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        row = fetchone(conn, "SELECT id,status FROM integration_outbox WHERE id=?", (event_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Integration event not found.")
        if row["status"] == "Completed":
            raise HTTPException(status_code=409, detail="Completed events are immutable and cannot be retried.")
        now = now_iso()
        conn.execute(
            """
            UPDATE integration_outbox
            SET status='Retry',next_attempt_at=?,last_error=NULL,dead_letter_at=NULL,
                locked_at=NULL,locked_by=NULL,updated_at=?
            WHERE id=?
            """,
            (now, now, event_id),
        )
        conn.commit()
        return {"ok": True, "event_id": event_id, "status": "Retry"}
    finally:
        conn.close()


@router.post("/process")
def process_integrations_now(
    limit: int = Query(default=25, ge=1, le=100),
    user: dict[str, Any] = Depends(require_roles("owner")),
) -> dict[str, Any]:
    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        return process_due_events(conn, limit=limit, worker_id=f"manual:{user.get('display_name') or 'owner'}")
    finally:
        conn.close()
