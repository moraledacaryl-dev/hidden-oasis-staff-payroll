from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.main import configured_db_path
from api.security import require_api_key, require_roles
from core.db import fetchall, fetchone, get_conn, now_iso
from core.integration_outbox import DESTINATION_ENV, ensure_integration_schema
from core.operations_v2_adapter import process_due_events

router = APIRouter(prefix="/api/v1/integrations", dependencies=[Depends(require_api_key)])


def _configured(destination: str) -> bool:
    url_env, token_env = DESTINATION_ENV[destination]
    return bool(os.getenv(url_env, "").strip() and os.getenv(token_env, "").strip())


def _summary(conn) -> dict[str, Any]:
    rows = fetchall(
        conn,
        "SELECT destination,status,COUNT(*) AS count FROM integration_outbox GROUP BY destination,status ORDER BY destination,status",
    )
    destinations: dict[str, dict[str, Any]] = {}
    for destination in DESTINATION_ENV:
        destinations[destination] = {
            "configured": _configured(destination),
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


@router.get("/readiness")
def integration_readiness(
    user: dict[str, Any] = Depends(require_roles("owner", "payroll")),
) -> dict[str, Any]:
    """Return a fail-closed activation assessment without exposing destination secrets."""
    conn = get_conn(configured_db_path())
    try:
        summary = _summary(conn)
        status_counts = {
            row["status"]: int(row["count"])
            for row in fetchall(
                conn,
                "SELECT status,COUNT(*) AS count FROM integration_outbox GROUP BY status",
            )
        }
        stale_processing = int(
            (fetchone(
                conn,
                """
                SELECT COUNT(*) AS count FROM integration_outbox
                WHERE status='Processing'
                  AND locked_at IS NOT NULL
                  AND datetime(locked_at) < datetime('now','-15 minutes')
                """,
            ) or {}).get("count") or 0
        )
        missing = [name for name, data in summary["destinations"].items() if not data["configured"]]
        dead_letters = status_counts.get("Dead Letter", 0)
        activation_enabled = os.getenv("STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED", "false").strip().lower() == "true"
        checks = [
            {
                "key": "destinations_configured",
                "ok": not missing,
                "detail": "All destination URL/token pairs are configured." if not missing else f"Missing: {', '.join(missing)}",
            },
            {
                "key": "no_dead_letters",
                "ok": dead_letters == 0,
                "detail": f"{dead_letters} dead-letter event(s).",
            },
            {
                "key": "no_stale_claims",
                "ok": stale_processing == 0,
                "detail": f"{stale_processing} processing event(s) locked for more than 15 minutes.",
            },
            {
                "key": "activation_flag",
                "ok": activation_enabled,
                "detail": "Activation is explicitly enabled." if activation_enabled else "Activation flag remains disabled.",
            },
        ]
        technical_ready = all(check["ok"] for check in checks if check["key"] != "activation_flag")
        return {
            "technical_ready": technical_ready,
            "activation_enabled": activation_enabled,
            "ready": technical_ready and activation_enabled,
            "checks": checks,
            "status_counts": status_counts,
            "destinations": summary["destinations"],
            "rollout_order": ["accounting", "operations", "pos", "inventory"],
            "note": "The worker must remain disabled until the canary verifier passes and activation is explicitly approved.",
        }
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
        if row["status"] in {"Completed", "Processing"}:
            raise HTTPException(
                status_code=409,
                detail="Completed events and events being processed cannot be retried.",
            )
        now = now_iso()
        updated = conn.execute(
            """
            UPDATE integration_outbox
            SET status='Retry',next_attempt_at=?,last_error=NULL,dead_letter_at=NULL,
                locked_at=NULL,locked_by=NULL,updated_at=?
            WHERE id=? AND status NOT IN ('Completed','Processing')
            """,
            (now, now, event_id),
        )
        if updated.rowcount != 1:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Integration event is no longer eligible for retry.")
        conn.commit()
        return {"ok": True, "event_id": event_id, "status": "Retry"}
    finally:
        conn.close()


class StaleEventRecoveryRequest(BaseModel):
    confirmation: str
    reason: str = Field(min_length=10, max_length=500)


@router.post("/events/{event_id}/recover-stale")
def recover_stale_event(
    event_id: int,
    payload: StaleEventRecoveryRequest,
    user: dict[str, Any] = Depends(require_roles("owner")),
) -> dict[str, Any]:
    """Explicit owner recovery for abandoned claims, never live claims.

    A worker can be terminated between claim and acknowledgement. The event
    must remain available for review and require an owner decision to retry.
    Destination receivers must enforce event-id idempotency because delivery
    may have succeeded just before the worker stopped.
    """
    if payload.confirmation != "RECOVER STALE EVENT":
        raise HTTPException(status_code=422, detail="Explicit recovery confirmation is required.")
    reason = payload.reason.strip()
    if len(reason) < 10:
        raise HTTPException(status_code=422, detail="A meaningful recovery reason is required.")

    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        existing = fetchone(conn, "SELECT id FROM integration_outbox WHERE id=?", (event_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Integration event not found.")
        now = now_iso()
        actor = str(user.get("display_name") or "Owner").strip()[:100]
        recovery_note = f"Owner stale-claim recovery by {actor}: {reason}"
        updated = conn.execute(
            """
            UPDATE integration_outbox
            SET status='Retry', next_attempt_at=?,
                last_error=CASE
                    WHEN last_error IS NULL OR TRIM(last_error)='' THEN ?
                    ELSE last_error || ' | ' || ?
                END,
                locked_at=NULL, locked_by=NULL, updated_at=?
            WHERE id=? AND status='Processing'
              AND locked_at IS NOT NULL
              AND datetime(locked_at) < datetime('now','-15 minutes')
            """,
            (now, recovery_note, recovery_note, now, event_id),
        )
        if updated.rowcount != 1:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail="Only claims locked for more than 15 minutes can be recovered.",
            )
        conn.commit()
        return {"ok": True, "event_id": event_id, "status": "Retry", "recovered_by": actor}
    finally:
        conn.close()


@router.post("/process")
def process_integrations_now(
    limit: int = Query(default=25, ge=1, le=100),
    user: dict[str, Any] = Depends(require_roles("owner")),
) -> dict[str, Any]:
    if os.getenv("STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED", "false").strip().lower() != "true":
        raise HTTPException(status_code=409, detail="Integration activation is disabled. Complete Pass 3 canary verification first.")
    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        return process_due_events(conn, limit=limit, worker_id=f"manual:{user.get('display_name') or 'owner'}")
    finally:
        conn.close()
