#!/usr/bin/env python3
"""Verify legacy schedule rows are normalized into editable scheduled_shifts.

This script is report-only. It does not create, update, hide, or delete rows.
It is intended to be run after importing/migrating schedule history and before
removing legacy schedule runtime reads.

Exit codes:
- 0: migration looks complete and safe for the checked scope;
- 1: blocking issues were found;
- 2: database/schema/input problem prevented verification.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(os.getenv("STAFF_PAYROLL_DB_PATH", "data/staff_payroll.sqlite"))

DATE_COLUMNS = ["work_date", "shift_date", "date", "schedule_date"]
START_COLUMNS = ["shift_start", "start_time", "time_in", "scheduled_in"]
END_COLUMNS = ["shift_end", "end_time", "time_out", "scheduled_out"]


@dataclass(frozen=True)
class LegacyMapping:
    date_col: str
    start_col: str
    end_col: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that legacy schedules have been migrated into scheduled_shifts.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path. Defaults to STAFF_PAYROLL_DB_PATH or data/staff_payroll.sqlite.")
    parser.add_argument("--start", help="Optional start date YYYY-MM-DD.")
    parser.add_argument("--end", help="Optional end date YYYY-MM-DD.")
    parser.add_argument("--employee-id", type=int, help="Optional employee id to check.")
    parser.add_argument("--show-samples", type=int, default=20, help="Maximum sample rows to print per issue type.")
    return parser.parse_args()


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int((row[0] if row else 0) or 0)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def first_existing(columns: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def legacy_mapping(conn: sqlite3.Connection) -> LegacyMapping | None:
    columns = table_columns(conn, "schedules")
    if not columns:
        return None
    date_col = first_existing(columns, DATE_COLUMNS)
    start_col = first_existing(columns, START_COLUMNS)
    end_col = first_existing(columns, END_COLUMNS)
    if not date_col or not start_col or not end_col or "employee_id" not in columns:
        return None
    return LegacyMapping(date_col=date_col, start_col=start_col, end_col=end_col)


def date_filters(alias: str, date_col: str, start: str | None, end: str | None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if start:
        clauses.append(f"date({alias}.{date_col}) >= date(?)")
        params.append(start)
    if end:
        clauses.append(f"date({alias}.{date_col}) <= date(?)")
        params.append(end)
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def print_samples(title: str, sample_rows: list[sqlite3.Row], limit: int) -> None:
    print(f"\n{title}: {len(sample_rows)} sample(s)")
    for row in sample_rows[:limit]:
        print("  " + dict_text(row))
    if len(sample_rows) > limit:
        print(f"  ... {len(sample_rows) - limit} more not shown")


def dict_text(row: sqlite3.Row) -> str:
    return ", ".join(f"{key}={row[key]!r}" for key in row.keys())


def main() -> int:
    args = parse_args()
    db_path = args.db.expanduser().resolve()

    try:
        conn = connect(db_path)
    except SystemExit as error:
        print(error)
        return 2

    try:
        if not table_exists(conn, "scheduled_shifts"):
            print("BLOCKER: scheduled_shifts table does not exist.")
            return 2

        if not table_exists(conn, "schedules"):
            print("No legacy schedules table found. Nothing to migrate.")
            print("result=pass")
            return 0

        mapping = legacy_mapping(conn)
        if not mapping:
            print("BLOCKER: schedules table exists but does not have usable employee/date/start/end columns.")
            print(f"columns={sorted(table_columns(conn, 'schedules'))}")
            return 2

        scheduled_columns = table_columns(conn, "scheduled_shifts")
        if "legacy_schedule_id" not in scheduled_columns:
            print("BLOCKER: scheduled_shifts.legacy_schedule_id is missing.")
            return 2

        date_sql, date_params = date_filters("s", mapping.date_col, args.start, args.end)
        employee_sql = " AND s.employee_id=?" if args.employee_id else ""
        employee_params: list[Any] = [args.employee_id] if args.employee_id else []
        scope_params = tuple(date_params + employee_params)

        legacy_total = scalar(
            conn,
            f"""
            SELECT COUNT(*)
            FROM schedules s
            WHERE 1=1 {date_sql} {employee_sql}
            """,
            scope_params,
        )
        invalid_legacy = rows(
            conn,
            f"""
            SELECT s.id AS legacy_id, s.employee_id, s.{mapping.date_col} AS shift_date,
                   s.{mapping.start_col} AS start_time, s.{mapping.end_col} AS end_time
            FROM schedules s
            WHERE 1=1 {date_sql} {employee_sql}
              AND (
                s.id IS NULL OR COALESCE(s.employee_id,0)=0
                OR COALESCE(s.{mapping.date_col},'')=''
                OR COALESCE(s.{mapping.start_col},'')=''
                OR COALESCE(s.{mapping.end_col},'')=''
              )
            ORDER BY s.{mapping.date_col}, s.id
            """,
            scope_params,
        )
        migrated_by_id = scalar(
            conn,
            f"""
            SELECT COUNT(*)
            FROM schedules s
            JOIN scheduled_shifts ss ON ss.legacy_schedule_id=s.id
            WHERE 1=1 {date_sql} {employee_sql}
            """,
            scope_params,
        )
        migrated_by_match = scalar(
            conn,
            f"""
            SELECT COUNT(*)
            FROM schedules s
            JOIN scheduled_shifts ss
              ON ss.employee_id=s.employee_id
             AND date(ss.shift_date)=date(s.{mapping.date_col})
             AND substr(ss.start_time,1,5)=substr(s.{mapping.start_col},1,5)
             AND substr(ss.end_time,1,5)=substr(s.{mapping.end_col},1,5)
            WHERE 1=1 {date_sql} {employee_sql}
            """,
            scope_params,
        )
        unmigrated = rows(
            conn,
            f"""
            SELECT s.id AS legacy_id, s.employee_id, s.{mapping.date_col} AS shift_date,
                   s.{mapping.start_col} AS start_time, s.{mapping.end_col} AS end_time
            FROM schedules s
            LEFT JOIN scheduled_shifts by_id ON by_id.legacy_schedule_id=s.id
            LEFT JOIN scheduled_shifts by_match
              ON by_match.employee_id=s.employee_id
             AND date(by_match.shift_date)=date(s.{mapping.date_col})
             AND substr(by_match.start_time,1,5)=substr(s.{mapping.start_col},1,5)
             AND substr(by_match.end_time,1,5)=substr(s.{mapping.end_col},1,5)
            WHERE 1=1 {date_sql} {employee_sql}
              AND COALESCE(s.employee_id,0)<>0
              AND COALESCE(s.{mapping.date_col},'')<>''
              AND COALESCE(s.{mapping.start_col},'')<>''
              AND COALESCE(s.{mapping.end_col},'')<>''
              AND by_id.id IS NULL
              AND by_match.id IS NULL
            ORDER BY s.{mapping.date_col}, s.employee_id, s.{mapping.start_col}, s.id
            """,
            scope_params,
        )
        duplicate_identity = rows(
            conn,
            """
            SELECT employee_id, shift_date, start_time, end_time, COUNT(*) AS count, GROUP_CONCAT(id) AS ids
            FROM scheduled_shifts
            GROUP BY employee_id, shift_date, start_time, end_time
            HAVING COUNT(*) > 1
            ORDER BY date(shift_date), employee_id, start_time
            """,
        )
        duplicate_legacy_id = rows(
            conn,
            """
            SELECT legacy_schedule_id, COUNT(*) AS count, GROUP_CONCAT(id) AS ids
            FROM scheduled_shifts
            WHERE legacy_schedule_id IS NOT NULL
            GROUP BY legacy_schedule_id
            HAVING COUNT(*) > 1
            ORDER BY legacy_schedule_id
            """,
        )
        ignored_migrated = rows(
            conn,
            """
            SELECT li.legacy_schedule_id, li.ignored_at, li.reason
            FROM legacy_schedule_ignores li
            LEFT JOIN scheduled_shifts ss ON ss.legacy_schedule_id=li.legacy_schedule_id
            WHERE ss.id IS NULL
            ORDER BY li.legacy_schedule_id
            """,
        ) if table_exists(conn, "legacy_schedule_ignores") else []

        print("Schedule migration verification")
        print(f"db={db_path}")
        print(f"scope_start={args.start or 'ALL'} scope_end={args.end or 'ALL'} employee_id={args.employee_id or 'ALL'}")
        print(f"legacy_total={legacy_total}")
        print(f"migrated_by_legacy_id={migrated_by_id}")
        print(f"matched_by_employee_date_time={migrated_by_match}")
        print(f"invalid_legacy_rows={len(invalid_legacy)}")
        print(f"unmigrated_valid_legacy_rows={len(unmigrated)}")
        print(f"scheduled_duplicate_identity_groups={len(duplicate_identity)}")
        print(f"scheduled_duplicate_legacy_id_groups={len(duplicate_legacy_id)}")
        print(f"ignored_without_migrated_shift={len(ignored_migrated)}")

        blockers = []
        if invalid_legacy:
            blockers.append("invalid legacy schedule rows")
            print_samples("INVALID LEGACY ROWS", invalid_legacy, args.show_samples)
        if unmigrated:
            blockers.append("unmigrated valid legacy schedule rows")
            print_samples("UNMIGRATED VALID LEGACY ROWS", unmigrated, args.show_samples)
        if duplicate_identity:
            blockers.append("duplicate scheduled_shifts by employee/date/time")
            print_samples("DUPLICATE SCHEDULED SHIFT IDENTITIES", duplicate_identity, args.show_samples)
        if duplicate_legacy_id:
            blockers.append("duplicate scheduled_shifts by legacy_schedule_id")
            print_samples("DUPLICATE LEGACY IDS", duplicate_legacy_id, args.show_samples)
        if ignored_migrated:
            blockers.append("legacy ignore rows without migrated scheduled_shift")
            print_samples("STALE LEGACY IGNORES", ignored_migrated, args.show_samples)

        if blockers:
            print("\nresult=fail")
            print("blockers=" + "; ".join(blockers))
            return 1

        print("\nresult=pass")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
