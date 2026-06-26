from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

from .db import fetchone, now_iso


def normalized_identifier(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _lock_seconds(failed_count: int) -> int:
    threshold = max(3, int(os.getenv("STAFF_PAYROLL_LOGIN_FAILURE_LIMIT", "5")))
    if failed_count < threshold:
        return 0
    exponent = min(5, failed_count - threshold)
    return min(3600, 60 * (2**exponent))


def lock_remaining_seconds(
    conn: sqlite3.Connection,
    identifier: str,
    ip_address: str,
) -> int:
    row = fetchone(
        conn,
        "SELECT locked_until FROM login_attempts WHERE identifier=? AND ip_address=?",
        (normalized_identifier(identifier), ip_address),
    )
    if not row or not row.get("locked_until"):
        return 0
    try:
        locked_until = datetime.fromisoformat(str(row["locked_until"]))
    except ValueError:
        return 0
    return max(0, int((locked_until - datetime.now()).total_seconds()))


def record_login_failure(
    conn: sqlite3.Connection,
    identifier: str,
    ip_address: str,
) -> int:
    key = normalized_identifier(identifier)
    row = fetchone(
        conn,
        "SELECT failed_count FROM login_attempts WHERE identifier=? AND ip_address=?",
        (key, ip_address),
    )
    failed_count = int((row or {}).get("failed_count") or 0) + 1
    lock_seconds = _lock_seconds(failed_count)
    locked_until = (
        (datetime.now() + timedelta(seconds=lock_seconds)).replace(microsecond=0).isoformat(sep=" ")
        if lock_seconds
        else None
    )
    conn.execute(
        """
        INSERT INTO login_attempts(identifier, ip_address, failed_count, last_failed_at, locked_until)
        VALUES(?,?,?,?,?)
        ON CONFLICT(identifier, ip_address)
        DO UPDATE SET failed_count=excluded.failed_count,
                      last_failed_at=excluded.last_failed_at,
                      locked_until=excluded.locked_until
        """,
        (key, ip_address, failed_count, now_iso(), locked_until),
    )
    conn.commit()
    return lock_seconds


def clear_login_failures(
    conn: sqlite3.Connection,
    identifier: str,
    ip_address: str,
) -> None:
    conn.execute(
        "DELETE FROM login_attempts WHERE identifier=? AND ip_address=?",
        (normalized_identifier(identifier), ip_address),
    )
    conn.commit()
