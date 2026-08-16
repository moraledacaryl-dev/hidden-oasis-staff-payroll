from __future__ import annotations

import json
import os
import socket
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from core.db import fetchall, fetchone, now_iso
from core.money import money_or_zero

STATUS_PENDING = "Pending"
STATUS_PROCESSING = "Processing"
STATUS_RETRY = "Retry"
STATUS_COMPLETED = "Completed"
STATUS_DEAD_LETTER = "Dead Letter"

DESTINATION_ENV = {
    "accounting": ("STAFF_PAYROLL_ACCOUNTING_SYNC_URL", "STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN"),
    "operations": ("STAFF_PAYROLL_OPERATIONS_SYNC_URL", "STAFF_PAYROLL_OPERATIONS_SYNC_TOKEN"),
    "pos": ("STAFF_PAYROLL_POS_SYNC_URL", "STAFF_PAYROLL_POS_SYNC_TOKEN"),
    "inventory": ("STAFF_PAYROLL_INVENTORY_SYNC_URL", "STAFF_PAYROLL_INVENTORY_SYNC_TOKEN"),
}

ACCOUNTING_EMPLOYEE_ENDPOINT = "/api/integrations/payroll/employees"
ACCOUNTING_FINANCIAL_ENDPOINT = "/api/integration-review/service-intake"
ACCOUNTING_FINANCIAL_EVENTS = {
    "payroll.run.approved",
    "payroll.run.paid",
    "payroll.13th_month.paid",
    "cash_advance.released",
    "cash_advance.repaid",
}

DEFAULT_ENDPOINTS = {
    "operations": "/api/integrations/staff/events",
    "pos": "/api/integrations/staff/employees",
    "inventory": "/api/v1/integrations/staff/employees",
}


def ensure_integration_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(integration_outbox)").fetchall()}
    if not columns:
        conn.execute(
            """
            CREATE TABLE integration_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destination TEXT NOT NULL,
                event_type TEXT NOT NULL,
                external_source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                source_type TEXT,
                source_id INTEGER,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 8,
                next_attempt_at TEXT,
                last_attempt_at TEXT,
                last_error TEXT,
                response_json TEXT,
                locked_at TEXT,
                locked_by TEXT,
                completed_at TEXT,
                dead_letter_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(destination, external_source, external_id)
            )
            """
        )
    elif "destination" not in columns:
        conn.execute("ALTER TABLE integration_outbox RENAME TO integration_outbox_legacy")
        conn.execute(
            """
            CREATE TABLE integration_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destination TEXT NOT NULL,
                event_type TEXT NOT NULL,
                external_source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                source_type TEXT,
                source_id INTEGER,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 8,
                next_attempt_at TEXT,
                last_attempt_at TEXT,
                last_error TEXT,
                response_json TEXT,
                locked_at TEXT,
                locked_by TEXT,
                completed_at TEXT,
                dead_letter_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(destination, external_source, external_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO integration_outbox(
                destination,event_type,external_source,external_id,source_type,source_id,
                payload_json,status,attempt_count,last_error,completed_at,created_at,updated_at
            )
            SELECT
                CASE WHEN event_type IN ('employee.sync','payroll.run.approved','payroll.run.paid','payroll.13th_month.paid','cash_advance.released','cash_advance.repaid')
                     THEN 'accounting' ELSE 'operations' END,
                event_type,external_source,external_id,source_type,source_id,payload_json,
                CASE status WHEN 'Ready' THEN 'Pending' WHEN 'Sent' THEN 'Completed' WHEN 'Error' THEN 'Retry' ELSE status END,
                attempt_count,last_error,sent_at,created_at,updated_at
            FROM integration_outbox_legacy
            """
        )
        conn.execute("DROP TABLE integration_outbox_legacy")
    else:
        additions = {
            "max_attempts": "INTEGER NOT NULL DEFAULT 8",
            "next_attempt_at": "TEXT",
            "last_attempt_at": "TEXT",
            "response_json": "TEXT",
            "locked_at": "TEXT",
            "locked_by": "TEXT",
            "completed_at": "TEXT",
            "dead_letter_at": "TEXT",
        }
        for column, definition in additions.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE integration_outbox ADD COLUMN {column} {definition}")
    # Normalize legacy delivery-state names that can remain in databases
    # which were upgraded after the destination-aware outbox schema already
    # existed. claim_events() intentionally processes only Pending/Retry.
    conn.execute(
        """
        UPDATE integration_outbox
        SET status = CASE status
            WHEN 'Ready' THEN 'Pending'
            WHEN 'Sent' THEN 'Completed'
            WHEN 'Error' THEN 'Retry'
            ELSE status
        END,
        completed_at = CASE
            WHEN status='Sent'
            THEN COALESCE(completed_at, updated_at)
            ELSE completed_at
        END
        WHERE status IN ('Ready', 'Sent', 'Error')
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_integration_outbox_delivery ON integration_outbox(status,next_attempt_at,destination,id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_integration_outbox_source ON integration_outbox(source_type,source_id,event_type)")
    conn.commit()


def enqueue_event(
    conn: sqlite3.Connection,
    *,
    destination: str,
    event_type: str,
    external_source: str,
    external_id: str,
    source_type: str | None,
    source_id: int | None,
    payload: dict[str, Any],
    max_attempts: int = 8,
) -> int:
    ensure_integration_schema(conn)
    now = now_iso()
    conn.execute(
        """
        INSERT INTO integration_outbox(
            destination,event_type,external_source,external_id,source_type,source_id,
            payload_json,status,attempt_count,max_attempts,next_attempt_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,'Pending',0,?,?,?,?)
        ON CONFLICT(destination,external_source,external_id) DO UPDATE SET
            event_type=excluded.event_type,
            source_type=excluded.source_type,
            source_id=excluded.source_id,
            payload_json=excluded.payload_json,
            max_attempts=excluded.max_attempts,
            status=CASE WHEN integration_outbox.status='Completed' THEN 'Completed' ELSE 'Pending' END,
            next_attempt_at=CASE WHEN integration_outbox.status='Completed' THEN integration_outbox.next_attempt_at ELSE excluded.next_attempt_at END,
            last_error=CASE WHEN integration_outbox.status='Completed' THEN integration_outbox.last_error ELSE NULL END,
            updated_at=excluded.updated_at
        """,
        (
            destination,
            event_type,
            external_source,
            external_id,
            source_type,
            source_id,
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
            max(1, int(max_attempts)),
            now,
            now,
            now,
        ),
    )
    row = fetchone(
        conn,
        "SELECT id FROM integration_outbox WHERE destination=? AND external_source=? AND external_id=?",
        (destination, external_source, external_id),
    )
    return int(row["id"])


def enqueue_employee_sync(conn: sqlite3.Connection, employee_id: int) -> list[int]:
    row = fetchone(
        conn,
        "SELECT id,employee_code,full_name,department,position,employment_type,status,updated_at FROM employees WHERE id=?",
        (employee_id,),
    )
    if not row:
        raise ValueError(f"Employee {employee_id} not found")
    generated_at = now_iso()
    employee = {
        "employee_code": row["employee_code"],
        "display_name": row["full_name"],
        "department": row.get("department"),
        "position": row.get("position"),
        "role": row.get("employment_type"),
        "active": row.get("status") not in {"Inactive", "Separated", "Terminated"},
        "primary_department": row.get("department"),
        "source_staff_id": row["id"],
    }
    version = str(row.get("updated_at") or generated_at).replace(" ", "T")
    envelope = {
        "external_source": "hidden_oasis_staff_payroll",
        "external_id": f"employee-sync:{employee_id}:{version}",
        "event_type": "employee.sync",
        "source_record_type": "Employee",
        "source_record_id": employee_id,
        "generated_at": generated_at,
        "schema_version": "2026-06-v1",
        "payload": {"employees": [employee]},
    }
    return [
        enqueue_event(
            conn,
            destination=destination,
            event_type="employee.sync",
            external_source=envelope["external_source"],
            external_id=envelope["external_id"],
            source_type="Employee",
            source_id=employee_id,
            payload=envelope,
        )
        for destination in DESTINATION_ENV
    ]


def destination_config(destination: str) -> tuple[str, str]:
    if destination not in DESTINATION_ENV:
        raise ValueError(f"Unsupported integration destination: {destination}")
    url_env, token_env = DESTINATION_ENV[destination]
    return os.getenv(url_env, "").strip(), os.getenv(token_env, "").strip()


def endpoint_for(destination: str, event_type: str) -> str:
    if destination == "accounting":
        if event_type == "employee.sync":
            return ACCOUNTING_EMPLOYEE_ENDPOINT
        if event_type in ACCOUNTING_FINANCIAL_EVENTS:
            return ACCOUNTING_FINANCIAL_ENDPOINT
        raise ValueError(f"Accounting does not accept {event_type}")
    endpoint = DEFAULT_ENDPOINTS.get(destination)
    if not endpoint:
        raise ValueError(f"No endpoint configured for {destination}")
    if destination in {"pos", "inventory"} and event_type != "employee.sync":
        raise ValueError(f"{destination} only accepts employee.sync during integration rollout")
    return endpoint


def _money(value: Any) -> float:
    return money_or_zero(value)


def _first_positive(*values: Any) -> float:
    for value in values:
        amount = _money(value)
        if amount > 0:
            return amount
    return 0.0


def canonical_accounting_payload(event_type: str, envelope: dict[str, Any]) -> dict[str, Any]:
    """Translate Staff's durable event envelope to Accounting's review contract."""
    if event_type not in ACCOUNTING_FINANCIAL_EVENTS:
        return envelope

    body = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
    totals = body.get("totals") if isinstance(body.get("totals"), dict) else {}
    run = body.get("run") if isinstance(body.get("run"), dict) else {}
    cash_advance = body.get("cash_advance") if isinstance(body.get("cash_advance"), dict) else {}
    repayment = body.get("repayment") if isinstance(body.get("repayment"), dict) else {}

    external_source = str(envelope.get("external_source") or "hidden_oasis_staff_payroll")
    external_id = str(envelope.get("external_id") or f"{event_type}:{body.get('id') or now_iso()}")
    source_type = str(envelope.get("source_record_type") or "PayrollEvent")
    source_id = str(envelope.get("source_record_id") or body.get("id") or run.get("id") or external_id)
    revision = int(envelope.get("source_revision") or body.get("source_revision") or 1)
    correlation_id = str(envelope.get("correlation_id") or external_id)
    proposed_account_id = body.get("accounting_account_id") or body.get("financial_account_id")

    financial_effect = "journal_only"
    amount = 0.0
    links: dict[str, Any] = {}
    proposed_journal: dict[str, Any] | None = None

    if event_type == "payroll.run.approved":
        amount = _first_positive(totals.get("net_pay"), totals.get("gross_pay"), run.get("net_pay"), run.get("gross_pay"))
        financial_effect = "payable"
        links = {
            "supplier_name": "Employees",
            "payable_type": "payroll",
            "due_date": run.get("payment_date") or body.get("payment_date"),
            "category": "Payroll",
        }
    elif event_type == "payroll.run.paid":
        amount = _first_positive(totals.get("net_pay"), run.get("net_pay"), body.get("amount"))
        financial_effect = "cash_out"
        links = {
            "category": "Payroll",
            "subcategory": "Net Pay",
            "payment_method": run.get("payment_method") or body.get("payment_method") or "bank_transfer",
            "counterparty_name": "Employees",
        }
    elif event_type == "payroll.13th_month.paid":
        amount = _first_positive(run.get("net_13th_pay"), totals.get("net_pay"), body.get("amount"))
        financial_effect = "cash_out"
        links = {
            "category": "Payroll",
            "subcategory": "13th Month Pay",
            "payment_method": run.get("payment_method") or body.get("payment_method") or "bank_transfer",
            "counterparty_name": "Employees",
        }
    elif event_type == "cash_advance.released":
        amount = _first_positive(cash_advance.get("amount"), body.get("amount"))
        financial_effect = "cash_out"
        links = {
            "category": "Employee Cash Advance",
            "subcategory": "Release",
            "payment_method": cash_advance.get("release_method") or body.get("payment_method") or "cash",
            "counterparty_name": cash_advance.get("employee_name") or body.get("employee_name"),
        }
    elif event_type == "cash_advance.repaid":
        amount = _first_positive(repayment.get("amount"), body.get("amount"))
        financial_effect = "cash_in"
        links = {
            "category": "Employee Cash Advance",
            "subcategory": "Repayment",
            "payment_method": repayment.get("payment_method") or body.get("payment_method") or "payroll_deduction",
            "counterparty_name": repayment.get("employee_name") or body.get("employee_name"),
        }

    return {
        "source_app": "staff",
        "source_event_id": external_id,
        "source_entity_type": source_type,
        "source_entity_id": source_id,
        "source_revision": revision,
        "financial_effect": financial_effect,
        "amount": amount,
        "currency": str(body.get("currency") or "PHP").upper(),
        "proposed_account_id": proposed_account_id,
        "proposed_journal": proposed_journal,
        "proposed_links": links,
        "payload": envelope,
        "idempotency_key": f"{external_source}:{external_id}:{revision}",
        "correlation_id": correlation_id,
    }


def _join_url(base: str, endpoint: str) -> str:
    return f"{base.rstrip('/')}/{endpoint.lstrip('/')}"


def _post(url: str, body: str, token: str, timeout: int) -> tuple[int, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Integration-Api-Key"] = token
    request = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def _backoff_seconds(attempt: int) -> int:
    return min(3600, 15 * (2 ** max(0, attempt - 1)))


def claim_events(conn: sqlite3.Connection, *, limit: int = 25, worker_id: str | None = None) -> list[dict[str, Any]]:
    ensure_integration_schema(conn)
    worker = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    now = now_iso()
    conn.execute("BEGIN IMMEDIATE")
    rows = fetchall(
        conn,
        """
        SELECT * FROM integration_outbox
        WHERE status IN ('Pending','Retry')
          AND (next_attempt_at IS NULL OR next_attempt_at<=?)
        ORDER BY id
        LIMIT ?
        """,
        (now, max(1, int(limit))),
    )
    for row in rows:
        conn.execute(
            "UPDATE integration_outbox SET status='Processing',locked_at=?,locked_by=?,updated_at=? WHERE id=? AND status IN ('Pending','Retry')",
            (now, worker, now, row["id"]),
        )
    conn.commit()
    return fetchall(
        conn,
        f"SELECT * FROM integration_outbox WHERE id IN ({','.join('?' for _ in rows)}) AND locked_by=? ORDER BY id" if rows else "SELECT * FROM integration_outbox WHERE 0",
        (*[row["id"] for row in rows], worker) if rows else (),
    )


def process_claimed_event(conn: sqlite3.Connection, row: dict[str, Any], *, timeout: int = 20) -> dict[str, Any]:
    event_id = int(row["id"])
    attempt = int(row.get("attempt_count") or 0) + 1
    max_attempts = int(row.get("max_attempts") or 8)
    destination = str(row["destination"])
    event_type = str(row["event_type"])
    base_url, token = destination_config(destination)
    now = now_iso()
    if not base_url:
        error = f"{destination} destination is not configured"
        conn.execute(
            "UPDATE integration_outbox SET status='Retry',attempt_count=?,last_attempt_at=?,last_error=?,locked_at=NULL,locked_by=NULL,next_attempt_at=?,updated_at=? WHERE id=?",
            (attempt, now, error, (datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat(sep=" "), now, event_id),
        )
        conn.commit()
        return {"id": event_id, "status": "Retry", "error": error}
    try:
        url = _join_url(base_url, endpoint_for(destination, event_type))
        envelope = json.loads(str(row["payload_json"]))
        outbound = canonical_accounting_payload(event_type, envelope) if destination == "accounting" else envelope
        status_code, response_body = _post(
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
            return {"id": event_id, "status": "Completed", "http_status": status_code, "url": url}
        retryable = status_code >= 500 or status_code in {408, 425, 429}
        error = f"HTTP {status_code}: {response_body[:1000]}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        retryable = True
        error = str(exc)
        status_code = None
    dead = (not retryable) or attempt >= max_attempts
    next_status = STATUS_DEAD_LETTER if dead else STATUS_RETRY
    next_at = None if dead else (datetime.now() + timedelta(seconds=_backoff_seconds(attempt))).replace(microsecond=0).isoformat(sep=" ")
    conn.execute(
        "UPDATE integration_outbox SET status=?,attempt_count=?,last_attempt_at=?,last_error=?,next_attempt_at=?,dead_letter_at=?,locked_at=NULL,locked_by=NULL,updated_at=? WHERE id=?",
        (next_status, attempt, now, error, next_at, now if dead else None, now, event_id),
    )
    conn.commit()
    return {"id": event_id, "status": next_status, "http_status": status_code, "error": error}


def process_due_events(conn: sqlite3.Connection, *, limit: int = 25, worker_id: str | None = None) -> dict[str, Any]:
    rows = claim_events(conn, limit=limit, worker_id=worker_id)
    results = [process_claimed_event(conn, row) for row in rows]
    return {
        "claimed": len(rows),
        "completed": sum(result["status"] == STATUS_COMPLETED for result in results),
        "failed": sum(result["status"] == STATUS_RETRY for result in results),
        "dead_letter": sum(result["status"] == STATUS_DEAD_LETTER for result in results),
        "results": results,
    }
