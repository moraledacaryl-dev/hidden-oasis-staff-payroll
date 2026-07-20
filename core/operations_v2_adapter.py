from __future__ import annotations

import json
import sqlite3
import urllib.error
from datetime import datetime, timedelta
from typing import Any

from core.db import now_iso
from core import integration_outbox as outbox

OPERATIONS_SOURCE_APP = "hidden_oasis_staff_payroll"
OPERATIONS_ENDPOINT = f"/api/integrations/v2/events/{OPERATIONS_SOURCE_APP}"

SUPPORTED_EVENT_TYPES = {
    "staff.operations.snapshot",
    "employee.status.changed",
    "attendance.exception.created",
    "ot.review.pending",
    "leave.request.pending",
    "cash_advance.request.pending",
    "payroll.ready_for_owner_review",
    "payroll.qa.warning",
    "annual_review.due",
    "memo.acknowledgment.pending",
    "task.submission.created",
    "shift.note.created",
    "fix.report.created",
    "guest.note.created",
}

EVENT_TYPE_ALIASES = {
    # Employee synchronization remains useful to Operations, but the v2
    # contract intentionally exposes it as an operational status change.
    "employee.sync": "employee.status.changed",
}


def _operation_event_type(event_type: str) -> str:
    resolved = EVENT_TYPE_ALIASES.get(event_type, event_type)
    if resolved not in SUPPORTED_EVENT_TYPES:
        raise ValueError(f"Operations v2 does not accept {event_type}")
    return resolved


def _first_text(mapping: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def canonical_operations_payload(event_type: str, envelope: dict[str, Any]) -> dict[str, Any]:
    """Translate Staff's durable envelope to the Operations v2 contract."""
    resolved_type = _operation_event_type(event_type)
    body = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    external_id = str(envelope.get("external_id") or f"{resolved_type}:{now_iso()}")
    source_type = envelope.get("source_record_type")
    source_id = envelope.get("source_record_id")

    title = _first_text(body, "title", "name")
    summary = _first_text(body, "summary", "note", "reason", "description")

    if event_type == "employee.sync":
        employees = body.get("employees") if isinstance(body.get("employees"), list) else []
        employee = employees[0] if employees and isinstance(employees[0], dict) else {}
        display_name = _first_text(employee, "display_name", "employee_code") or "Employee"
        title = title or f"Employee status updated: {display_name}"
        active = employee.get("active")
        status_text = "active" if active is True else "inactive" if active is False else "updated"
        summary = summary or f"Operational employee identity is {status_text}."

    if not title:
        title = resolved_type.replace(".", " ").replace("_", " ").title()

    priority = _first_text(body, "priority") or "Normal"
    occurred_at = envelope.get("generated_at") or envelope.get("occurred_at")

    payload: dict[str, Any] = {
        "event_id": external_id,
        "event_type": resolved_type,
        "schema_version": 1,
        "priority": priority,
        "title": title,
        "summary": summary,
        "payload": body,
        "metadata": {
            "external_source": envelope.get("external_source") or OPERATIONS_SOURCE_APP,
            "original_event_type": event_type,
            "staff_schema_version": envelope.get("schema_version"),
        },
    }
    if occurred_at:
        payload["occurred_at"] = occurred_at
    if source_type or source_id is not None:
        payload["subject"] = {
            "type": str(source_type) if source_type else None,
            "id": str(source_id) if source_id is not None else None,
        }
    correlation_id = envelope.get("correlation_id")
    if correlation_id:
        payload["correlation_id"] = str(correlation_id)
    department_id = body.get("department_id")
    if department_id is not None:
        try:
            payload["department_id"] = int(department_id)
        except (TypeError, ValueError):
            pass
    return payload


def _process_operations_event(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    timeout: int = 20,
) -> dict[str, Any]:
    event_id = int(row["id"])
    attempt = int(row.get("attempt_count") or 0) + 1
    max_attempts = int(row.get("max_attempts") or 8)
    base_url, token = outbox.destination_config("operations")
    now = now_iso()

    if not base_url:
        error = "operations destination is not configured"
        conn.execute(
            "UPDATE integration_outbox SET status='Retry',attempt_count=?,last_attempt_at=?,last_error=?,locked_at=NULL,locked_by=NULL,next_attempt_at=?,updated_at=? WHERE id=?",
            (
                attempt,
                now,
                error,
                (datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat(sep=" "),
                now,
                event_id,
            ),
        )
        conn.commit()
        return {"id": event_id, "status": outbox.STATUS_RETRY, "error": error}

    status_code: int | None = None
    try:
        envelope = json.loads(str(row["payload_json"]))
        outbound = canonical_operations_payload(str(row["event_type"]), envelope)
        url = outbox._join_url(base_url, OPERATIONS_ENDPOINT)
        status_code, response_body = outbox._post(
            url,
            json.dumps(outbound, ensure_ascii=False, sort_keys=True, default=str),
            token,
            timeout,
        )
        parsed = json.loads(response_body or "{}") if response_body else {}
        duplicate = status_code == 409 or (
            isinstance(parsed, dict)
            and parsed.get("status") in {"already_applied", "Already Applied"}
        )
        if 200 <= status_code < 300 or duplicate:
            conn.execute(
                "UPDATE integration_outbox SET status='Completed',attempt_count=?,last_attempt_at=?,last_error=NULL,response_json=?,completed_at=?,locked_at=NULL,locked_by=NULL,updated_at=? WHERE id=?",
                (attempt, now, response_body, now, now, event_id),
            )
            conn.commit()
            return {"id": event_id, "status": outbox.STATUS_COMPLETED, "http_status": status_code, "url": url}
        retryable = status_code >= 500 or status_code in {408, 425, 429}
        error = f"HTTP {status_code}: {response_body[:1000]}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        retryable = True
        error = str(exc)

    dead = (not retryable) or attempt >= max_attempts
    next_status = outbox.STATUS_DEAD_LETTER if dead else outbox.STATUS_RETRY
    next_at = None if dead else (
        datetime.now() + timedelta(seconds=outbox._backoff_seconds(attempt))
    ).replace(microsecond=0).isoformat(sep=" ")
    conn.execute(
        "UPDATE integration_outbox SET status=?,attempt_count=?,last_attempt_at=?,last_error=?,next_attempt_at=?,dead_letter_at=?,locked_at=NULL,locked_by=NULL,updated_at=? WHERE id=?",
        (next_status, attempt, now, error, next_at, now if dead else None, now, event_id),
    )
    conn.commit()
    return {"id": event_id, "status": next_status, "http_status": status_code, "error": error}


def process_due_events(
    conn: sqlite3.Connection,
    *,
    limit: int = 25,
    worker_id: str | None = None,
) -> dict[str, Any]:
    rows = outbox.claim_events(conn, limit=limit, worker_id=worker_id)
    results = [
        _process_operations_event(conn, row)
        if str(row.get("destination")) == "operations"
        else outbox.process_claimed_event(conn, row)
        for row in rows
    ]
    return {
        "claimed": len(rows),
        "completed": sum(result["status"] == outbox.STATUS_COMPLETED for result in results),
        "failed": sum(result["status"] == outbox.STATUS_RETRY for result in results),
        "dead_letter": sum(result["status"] == outbox.STATUS_DEAD_LETTER for result in results),
        "results": results,
    }
