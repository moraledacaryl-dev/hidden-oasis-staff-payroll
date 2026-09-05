#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(os.getenv("STAFF_PAYROLL_DB_PATH", "data/staff_payroll.sqlite"))


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def ensure_ignore_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_schedule_ignores (
            legacy_schedule_id INTEGER PRIMARY KEY,
            ignored_by TEXT,
            ignored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reason TEXT
        )
        """
    )


def exact_duplicate_groups(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not table_exists(conn, "scheduled_shifts"):
        return []
    return rows(
        conn,
        """
        SELECT employee_id, shift_date, start_time, end_time,
               position, department, break_minutes, status,
               COALESCE(notes, '') AS notes_key,
               COALESCE(legacy_schedule_id, -1) AS legacy_key,
               source,
               COALESCE(review_status, '') AS review_status_key,
               COALESCE(review_reason, '') AS review_reason_key,
               COALESCE(reviewed_by, '') AS reviewed_by_key,
               COALESCE(reviewed_at, '') AS reviewed_at_key,
               approved_exception,
               COUNT(*) AS c,
               GROUP_CONCAT(id) AS ids
        FROM scheduled_shifts
        GROUP BY employee_id, shift_date, start_time, end_time,
                 position, department, break_minutes, status,
                 COALESCE(notes, ''), COALESCE(legacy_schedule_id, -1), source,
                 COALESCE(review_status, ''), COALESCE(review_reason, ''),
                 COALESCE(reviewed_by, ''), COALESCE(reviewed_at, ''), approved_exception
        HAVING COUNT(*) > 1
        ORDER BY shift_date, employee_id, start_time
        """,
    )


def same_time_groups(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not table_exists(conn, "scheduled_shifts"):
        return []
    return rows(
        conn,
        """
        SELECT employee_id, shift_date, start_time, end_time,
               COUNT(*) AS c, GROUP_CONCAT(id) AS ids
        FROM scheduled_shifts
        GROUP BY employee_id, shift_date, start_time, end_time
        HAVING COUNT(*) > 1
        ORDER BY shift_date, employee_id, start_time
        """,
    )


def linked_time_log_ids(conn: sqlite3.Connection, shift_id: int) -> list[int]:
    if not table_exists(conn, "time_logs"):
        return []
    return [
        int(row["id"])
        for row in rows(
            conn,
            "SELECT id FROM time_logs WHERE scheduled_shift_id=? ORDER BY id",
            (shift_id,),
        )
    ]


def choose_keep_id(conn: sqlite3.Connection, ids: list[int]) -> int:
    linked = [shift_id for shift_id in ids if linked_time_log_ids(conn, shift_id)]
    if len(linked) > 1:
        raise RuntimeError(
            "Refusing duplicate cleanup because multiple equivalent shifts own linked time logs: "
            + ",".join(str(item) for item in linked)
        )
    if linked:
        return linked[0]
    return max(ids)


def ensure_change_log_table(conn: sqlite3.Connection) -> None:
    if table_exists(conn, "schedule_change_logs"):
        return
    conn.execute(
        """
        CREATE TABLE schedule_change_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            change_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            employee_id INTEGER,
            work_date TEXT,
            payroll_run_id INTEGER,
            before_json TEXT,
            after_json TEXT,
            changed_by TEXT,
            changed_at TEXT NOT NULL,
            undone_at TEXT,
            undone_by TEXT,
            reason_category TEXT,
            reason_note TEXT,
            attachment_ref TEXT
        )
        """
    )


def audit_delete(conn: sqlite3.Connection, shift: sqlite3.Row) -> None:
    ensure_change_log_table(conn)
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(schedule_change_logs)").fetchall()}
    if "reason_category" not in columns:
        conn.execute("ALTER TABLE schedule_change_logs ADD COLUMN reason_category TEXT")
    if "reason_note" not in columns:
        conn.execute("ALTER TABLE schedule_change_logs ADD COLUMN reason_note TEXT")
    before = json.dumps(dict(shift), sort_keys=True, separators=(",", ":"), default=str)
    conn.execute(
        """
        INSERT INTO schedule_change_logs(
            change_type, entity_type, entity_id, employee_id, work_date,
            before_json, after_json, changed_by, changed_at, reason_category, reason_note
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, datetime('now', 'localtime'), ?, ?)
        """,
        (
            "Cleanup exact duplicate scheduled shift",
            "scheduled_shift",
            int(shift["id"]),
            int(shift["employee_id"]),
            str(shift["shift_date"]),
            before,
            "cleanup-script",
            "data_integrity",
            "Removed redundant schedule row after semantic duplicate verification.",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit schedule duplicate/migration issues. Default is report-only.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply safe cleanup only for semantically exact duplicate scheduled_shifts and migrated legacy rows.",
    )
    args = parser.parse_args()

    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        exact_dupes = exact_duplicate_groups(conn)
        same_time = same_time_groups(conn)
        legacy_dupes = rows(
            conn,
            """
            SELECT legacy_schedule_id, COUNT(*) AS c, GROUP_CONCAT(id) AS ids
            FROM scheduled_shifts
            WHERE legacy_schedule_id IS NOT NULL
            GROUP BY legacy_schedule_id
            HAVING COUNT(*) > 1
            ORDER BY legacy_schedule_id
            """,
        ) if table_exists(conn, "scheduled_shifts") else []

        print(f"exact_duplicate_groups={len(exact_dupes)}")
        for row in exact_dupes:
            print(
                f"  exact employee={row['employee_id']} date={row['shift_date']} "
                f"{row['start_time']}-{row['end_time']} ids={row['ids']}"
            )
        print(f"same_time_groups={len(same_time)}")
        for row in same_time:
            print(
                f"  review employee={row['employee_id']} date={row['shift_date']} "
                f"{row['start_time']}-{row['end_time']} ids={row['ids']}"
            )
        print(f"legacy_duplicate_groups={len(legacy_dupes)}")
        for row in legacy_dupes:
            print(f"  legacy_id={row['legacy_schedule_id']} ids={row['ids']}")

        if not args.apply:
            print("report_only=true")
            return 0

        ensure_ignore_table(conn)
        deleted_ids: set[int] = set()

        for row in exact_dupes:
            ids = [int(x) for x in str(row["ids"]).split(",") if x]
            keep = choose_keep_id(conn, ids)
            for old_id in ids:
                if old_id == keep:
                    continue
                if linked_time_log_ids(conn, old_id):
                    raise RuntimeError(f"Refusing to delete scheduled_shift {old_id}: linked time_logs exist")
                shift = conn.execute("SELECT * FROM scheduled_shifts WHERE id=?", (old_id,)).fetchone()
                if shift is None:
                    continue
                audit_delete(conn, shift)
                conn.execute("DELETE FROM scheduled_shifts WHERE id=?", (old_id,))
                deleted_ids.add(old_id)

        for row in legacy_dupes:
            ids = [int(x) for x in str(row["ids"]).split(",") if x and int(x) not in deleted_ids]
            if len(ids) <= 1:
                continue
            keep = choose_keep_id(conn, ids)
            for old_id in ids:
                if old_id == keep:
                    continue
                if linked_time_log_ids(conn, old_id):
                    raise RuntimeError(f"Refusing to delete scheduled_shift {old_id}: linked time_logs exist")
                shift = conn.execute("SELECT * FROM scheduled_shifts WHERE id=?", (old_id,)).fetchone()
                if shift is None:
                    continue
                audit_delete(conn, shift)
                conn.execute("DELETE FROM scheduled_shifts WHERE id=?", (old_id,))
                deleted_ids.add(old_id)

        hidden = 0
        if table_exists(conn, "schedules"):
            migrated_legacy_ids = rows(conn, "SELECT DISTINCT legacy_schedule_id FROM scheduled_shifts WHERE legacy_schedule_id IS NOT NULL")
            for item in migrated_legacy_ids:
                legacy_id = item["legacy_schedule_id"]
                if legacy_id is not None:
                    before_changes = conn.total_changes
                    conn.execute(
                        "INSERT OR IGNORE INTO legacy_schedule_ignores(legacy_schedule_id, ignored_by, reason) VALUES (?, 'cleanup-script', 'Migrated to scheduled_shifts')",
                        (int(legacy_id),),
                    )
                    hidden += int(conn.total_changes > before_changes)

        conn.commit()
        print(
            f"applied=true deleted_scheduled_shifts={len(deleted_ids)} "
            f"deleted_ids={','.join(str(item) for item in sorted(deleted_ids)) or '-'} "
            f"migrated_legacy_hidden={hidden}"
        )
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
