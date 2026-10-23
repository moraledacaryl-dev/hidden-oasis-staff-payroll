from __future__ import annotations

"""Read-only triage for possibly interrupted Staff integration deliveries.

An old Processing claim has an UNKNOWN delivery outcome. It is not evidence
that Accounting/Operations accepted or rejected the event. Never replay it
automatically: doing so could duplicate financial postings.
"""

import argparse
import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from core.observability import parse_timestamp_utc, utc_now


def inspect_claims(db_path: Path, *, stale_minutes: int = 15) -> dict:
    if stale_minutes < 1:
        raise ValueError("stale_minutes must be positive")
    if not db_path.is_absolute() or not db_path.is_file():
        raise ValueError("An existing absolute database file is required")
    uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "integration_outbox" not in tables:
            raise ValueError("Durable integration outbox is unavailable")
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(integration_outbox)")
        }
        required = {"status", "locked_at", "destination"}
        if not required.issubset(columns):
            raise ValueError("Durable integration outbox schema is incomplete")
        rows = conn.execute(
            "SELECT destination, locked_at FROM integration_outbox WHERE status='Processing'"
        ).fetchall()
        threshold = utc_now() - timedelta(minutes=stale_minutes)
        counts = {}
        suspicious = 0
        invalid_lock = 0
        for row in rows:
            destination = str(row["destination"] or "unknown")
            if destination not in {"accounting", "operations", "pos", "inventory"}:
                destination = "other"
            entry = counts.setdefault(
                destination, {"processing": 0, "stale_or_unknown": 0}
            )
            entry["processing"] += 1
            try:
                locked_at = parse_timestamp_utc(row["locked_at"])
                stale = locked_at < threshold
            except (ValueError, TypeError, OverflowError):
                stale = True
                invalid_lock += 1
            if stale:
                suspicious += 1
                entry["stale_or_unknown"] += 1
        conn.rollback()
        return {
            "status": "manual_review_required" if suspicious else "no_stale_claims_found",
            "processing_total": len(rows),
            "stale_or_unknown_total": suspicious,
            "invalid_lock_timestamp_total": invalid_lock,
            "threshold_minutes": stale_minutes,
            "destinations": dict(sorted(counts.items())),
            "automatic_replay_authorized": False,
            "accounting_posting_authorized": False,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only stalled outbox audit")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--stale-minutes", type=int, default=15)
    args = parser.parse_args()
    try:
        report = inspect_claims(args.db, stale_minutes=args.stale_minutes)
    except (ValueError, sqlite3.Error, OSError) as exc:
        # Avoid leaking employee details, contents, credentials or DB paths.
        print(json.dumps({"status": "audit_unavailable", "reason": type(exc).__name__}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 1 if report["stale_or_unknown_total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
