#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("data/staff_payroll.sqlite")


def ensure_column(conn: sqlite3.Connection, column: str, definition: str) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(payroll_runs)").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE payroll_runs ADD COLUMN {column} {definition}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill payroll revision parent links from existing run summaries.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_column(conn, "revision_of_run_id", "INTEGER")
        ensure_column(conn, "revision_reason", "TEXT")
        rows = conn.execute(
            "SELECT id, validation_summary, revision_of_run_id FROM payroll_runs ORDER BY id"
        ).fetchall()
        updates: list[tuple[int, int]] = []
        for row in rows:
            if row["revision_of_run_id"]:
                continue
            summary = str(row["validation_summary"] or "")
            match = re.search(r"Revision of payroll run #(\d+)", summary)
            if match:
                updates.append((int(row["id"]), int(match.group(1))))
        print(f"revision_links_to_backfill={len(updates)}")
        for run_id, parent_id in updates:
            print(f"  run_id={run_id} revision_of_run_id={parent_id}")
            if args.apply:
                conn.execute("UPDATE payroll_runs SET revision_of_run_id=? WHERE id=?", (parent_id, run_id))
        if args.apply:
            conn.commit()
            print("applied=true")
        else:
            print("report_only=true")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
