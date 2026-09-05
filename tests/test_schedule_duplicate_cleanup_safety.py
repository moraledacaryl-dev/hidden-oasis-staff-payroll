from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path("scripts/audit_and_cleanup_schedule_duplicates.py")


def load_script_module():
    spec = importlib.util.spec_from_file_location("schedule_duplicate_cleanup", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load duplicate cleanup script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE scheduled_shifts (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER NOT NULL,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            position TEXT,
            department TEXT,
            break_minutes INTEGER,
            status TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            legacy_schedule_id INTEGER,
            source TEXT,
            review_status TEXT,
            review_reason TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_exception INTEGER DEFAULT 0
        );
        CREATE TABLE time_logs (
            id INTEGER PRIMARY KEY,
            scheduled_shift_id INTEGER,
            employee_id INTEGER,
            work_date TEXT
        );
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
        );
        """
    )


def insert_shift(conn: sqlite3.Connection, shift_id: int, *, position: str, department: str) -> None:
    conn.execute(
        """
        INSERT INTO scheduled_shifts(
            id, employee_id, shift_date, start_time, end_time, position, department,
            break_minutes, status, notes, created_at, updated_at, legacy_schedule_id,
            source, review_status, review_reason, reviewed_by, reviewed_at, approved_exception
        ) VALUES (?, 9, '2026-09-01', '07:00', '16:00', ?, ?, 60, 'Draft', NULL,
                  '2026-09-04 05:43:39', '2026-09-04 05:43:39', NULL,
                  'planned', NULL, NULL, NULL, NULL, 0)
        """,
        (shift_id, position, department),
    )


class ScheduleDuplicateCleanupSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_script_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "payroll.sqlite"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        create_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_same_time_different_assignment_is_not_exact_duplicate(self) -> None:
        insert_shift(self.conn, 608, position="Receptionist", department="Reception")
        insert_shift(self.conn, 671, position="Receptionist", department="Kitchen")
        self.conn.commit()

        exact = self.module.exact_duplicate_groups(self.conn)
        same_time = self.module.same_time_groups(self.conn)

        self.assertEqual(exact, [])
        self.assertEqual(len(same_time), 1)
        self.assertEqual(same_time[0]["ids"], "608,671")

    def test_identical_rows_are_exact_duplicates(self) -> None:
        insert_shift(self.conn, 1343, position="Housekeeper", department="Housekeeping")
        insert_shift(self.conn, 1344, position="Housekeeper", department="Housekeeping")
        self.conn.commit()

        exact = self.module.exact_duplicate_groups(self.conn)

        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["ids"], "1343,1344")

    def test_choose_keep_id_preserves_the_only_linked_shift(self) -> None:
        insert_shift(self.conn, 1343, position="Housekeeper", department="Housekeeping")
        insert_shift(self.conn, 1344, position="Housekeeper", department="Housekeeping")
        self.conn.execute(
            "INSERT INTO time_logs(id, scheduled_shift_id, employee_id, work_date) VALUES (1, 1343, 9, '2026-09-01')"
        )
        self.conn.commit()

        self.assertEqual(self.module.choose_keep_id(self.conn, [1343, 1344]), 1343)

    def test_choose_keep_id_refuses_when_multiple_duplicates_own_logs(self) -> None:
        insert_shift(self.conn, 1343, position="Housekeeper", department="Housekeeping")
        insert_shift(self.conn, 1344, position="Housekeeper", department="Housekeeping")
        self.conn.execute(
            "INSERT INTO time_logs(id, scheduled_shift_id, employee_id, work_date) VALUES (1, 1343, 9, '2026-09-01')"
        )
        self.conn.execute(
            "INSERT INTO time_logs(id, scheduled_shift_id, employee_id, work_date) VALUES (2, 1344, 9, '2026-09-01')"
        )
        self.conn.commit()

        with self.assertRaises(RuntimeError):
            self.module.choose_keep_id(self.conn, [1343, 1344])

    def test_audit_delete_records_before_state(self) -> None:
        insert_shift(self.conn, 1343, position="Housekeeper", department="Housekeeping")
        shift = self.conn.execute("SELECT * FROM scheduled_shifts WHERE id=1343").fetchone()
        assert shift is not None

        self.module.audit_delete(self.conn, shift)
        row = self.conn.execute(
            "SELECT change_type, entity_id, reason_category, before_json, after_json FROM schedule_change_logs"
        ).fetchone()

        self.assertEqual(row["change_type"], "Cleanup exact duplicate scheduled shift")
        self.assertEqual(row["entity_id"], 1343)
        self.assertEqual(row["reason_category"], "data_integrity")
        self.assertIn('"id":1343', row["before_json"])
        self.assertIsNone(row["after_json"])


if __name__ == "__main__":
    unittest.main()
