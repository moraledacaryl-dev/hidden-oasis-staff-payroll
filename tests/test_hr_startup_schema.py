from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from core.db import get_conn


def _startup_with_only_real_hr_schema(server, db_path: Path) -> None:
    with (
        patch.object(server, "validate_runtime_environment", return_value=None),
        patch.object(server, "configured_db_path", return_value=db_path),
        patch.object(server, "init_db", return_value=None),
        patch.object(server, "ensure_payroll_adjustment_schema", return_value=None),
        patch.object(server, "ensure_schedule_schema", return_value=None),
        patch.object(server, "ensure_schedule_change_log_schema", return_value=None),
        patch.object(server, "ensure_workflow_schema", return_value=None),
        patch.object(server, "ensure_integration_schema", return_value=None),
        patch.object(server, "ensure_legacy_integration_writer_compatibility", return_value=None),
        patch.object(server, "reconcile_unlinked_split_shift_logs", return_value=None),
    ):
        server.initialize_runtime()


def test_runtime_initializes_hr_schema_before_traffic() -> None:
    from api import server

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "hr-startup.sqlite"
        _startup_with_only_real_hr_schema(server, db_path)

        conn = get_conn(db_path)
        try:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "leave_types" in tables
            assert "employee_leave_entitlements" in tables
            assert "leave_requests" in tables
            assert "hr_records" in tables

            entitlement_columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_info(employee_leave_entitlements)"
                ).fetchall()
            }
            assert "effective_start" in entitlement_columns
            assert "effective_end" in entitlement_columns

            leave_request_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(leave_requests)").fetchall()
            }
            assert "decision_note" in leave_request_columns

            hr_indexes = {
                str(row[1])
                for row in conn.execute("PRAGMA index_list(hr_records)").fetchall()
            }
            assert "idx_hr_records_employee" in hr_indexes
            assert "idx_hr_records_type" in hr_indexes
        finally:
            conn.close()


def test_startup_repairs_legacy_hr_tables() -> None:
    from api import server

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "legacy-hr.sqlite"
        conn = get_conn(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE leave_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );
                CREATE TABLE employee_leave_entitlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    leave_type_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    UNIQUE(employee_id, leave_type_id, year)
                );
                CREATE TABLE leave_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    start_date TEXT,
                    end_date TEXT
                );
                CREATE TABLE hr_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        _startup_with_only_real_hr_schema(server, db_path)

        conn = get_conn(db_path)
        try:
            entitlement_columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_info(employee_leave_entitlements)"
                ).fetchall()
            }
            assert {"credits", "used", "entitled", "effective_start", "effective_end"} <= entitlement_columns

            leave_request_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(leave_requests)").fetchall()
            }
            assert {"leave_type_id", "days", "paid", "status", "decision_note"} <= leave_request_columns

            hr_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(hr_records)").fetchall()
            }
            assert {"record_type", "record_date", "subject", "severity", "status", "rating"} <= hr_columns
        finally:
            conn.close()
