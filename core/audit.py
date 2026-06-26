from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import now_iso


def ensure_audit_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT,
            action TEXT NOT NULL,
            table_name TEXT,
            record_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_record ON audit_logs(table_name, record_id)"
    )


def log_audit(
    conn: sqlite3.Connection,
    *,
    actor: str | None,
    action: str,
    table_name: str | None = None,
    record_id: int | None = None,
    details: dict[str, Any] | str | None = None,
) -> None:
    ensure_audit_schema(conn)
    encoded = json.dumps(details, sort_keys=True, default=str) if isinstance(details, dict) else details
    conn.execute(
        """
        INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at)
        VALUES(?,?,?,?,?,?)
        """,
        (actor, action, table_name, record_id, encoded, now_iso()),
    )
