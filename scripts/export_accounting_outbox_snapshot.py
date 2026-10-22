#!/usr/bin/env python3
"""Read-only, confidential Staff financial outbox identity snapshot for Accounting.

Does not send/retry an event or touch financial records. It exports ONLY
event_type, external_id, source_revision and status, not payroll amounts,
employee identities, private payloads or transport credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

FINANCIAL_TYPES = (
    "payroll.run.approved",
    "payroll.run.paid",
    "payroll.13th_month.paid",
    "cash_advance.released",
    "cash_advance.repaid",
)


def export_staff_outbox(conn: sqlite3.Connection) -> dict:
    """Require a caller-owned, read-only SQLite snapshot; never paginate."""
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in FINANCIAL_TYPES)
    rows = conn.execute(
        f"""SELECT event_type, external_id, payload_json, status
            FROM integration_outbox
            WHERE destination = 'accounting'
              AND external_source = 'hidden_oasis_staff_payroll'
              AND event_type IN ({placeholders})
            ORDER BY id""",
        FINANCIAL_TYPES,
    )
    events = []
    for row in rows:
        try:
            envelope = json.loads(row["payload_json"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid Staff financial outbox envelope; no incomplete export.") from exc
        if not isinstance(envelope, dict):
            raise ValueError("Invalid Staff financial outbox envelope object.")
        body = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
        # Exact revision derivation matches core.integration_outbox.canonical_accounting_payload.
        revision = int(envelope.get("source_revision") or body.get("source_revision") or 1)
        if revision < 1:
            raise ValueError("Staff financial event has an invalid source revision.")
        if str(envelope.get("external_id") or "").strip() != str(row["external_id"] or "").strip():
            raise ValueError("Staff outbox envelope and indexed external event ID disagree.")
        if not str(row["external_id"] or "").strip():
            raise ValueError("Staff financial outbox has no stable external event ID.")
        events.append({
            "destination": "accounting",
            "event_type": row["event_type"],
            "external_id": row["external_id"],
            "source_revision": revision,
            "status": row["status"],
        })
    return {
        "source": "staff",
        "export_type": "staff_financial_outbox_identities",
        # A complete SQL scan is not a coordinated snapshot of Accounting.
        # The operator must independently establish same-window coverage.
        "complete_for_window": False,
        "full_source_scan": True,
        "events": events,
        "caveat": (
            "No Accounting database queried. Source scan does not establish "
            "receiver coverage, accepted posting, cash custody or bank settlement."
        ),
    }


def write_private(path: Path, report: dict) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    finally:
        if fd is not None:
            os.close(fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(os.environ["STAFF_PAYROLL_DB_PATH"])
                        if os.getenv("STAFF_PAYROLL_DB_PATH") else None)
    parser.add_argument("--output", type=Path, required=True,
                        help="New protected JSON path; will never overwrite")
    args = parser.parse_args(argv)
    if args.db is None or not args.db.is_absolute() or not args.db.is_file():
        parser.error("--db must be an existing absolute Staff SQLite path")
    if not args.output.is_absolute():
        parser.error("--output must be an absolute path")
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        report = export_staff_outbox(conn)
    write_private(args.output, report)
    print(f"STAFF ACCOUNTING SOURCE IDENTITY EXPORT: PASS | events={len(report['events'])}")
    print("ACCOUNTING RECEIPTS, POSTINGS AND CROSS-APP COMPLETENESS: NOT VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
