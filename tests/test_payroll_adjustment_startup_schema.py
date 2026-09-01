from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from core.db import get_conn


def test_runtime_initializes_payroll_adjustment_schema_before_traffic() -> None:
    from api import server

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "startup.sqlite"

        with (
            patch.object(server, "validate_runtime_environment", return_value=None),
            patch.object(server, "configured_db_path", return_value=db_path),
            patch.object(server, "ensure_schedule_schema", return_value=None),
            patch.object(server, "ensure_schedule_change_log_schema", return_value=None),
            patch.object(server, "ensure_workflow_schema", return_value=None),
            patch.object(server, "ensure_integration_schema", return_value=None),
            patch.object(server, "ensure_legacy_integration_writer_compatibility", return_value=None),
            patch.object(server, "reconcile_unlinked_split_shift_logs", return_value=None),
        ):
            server.initialize_runtime()

        conn = get_conn(db_path)
        try:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "payroll_item_adjustments" in tables
            assert "payroll_adjustment_events" in tables

            adjustment_columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_info(payroll_item_adjustments)"
                ).fetchall()
            }
            assert "cash_advance_note" in adjustment_columns
            assert "version" in adjustment_columns

            event_indexes = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA index_list(payroll_adjustment_events)"
                ).fetchall()
            }
            assert "idx_payroll_adjustment_events_run" in event_indexes
            assert "idx_payroll_adjustment_events_item" in event_indexes
        finally:
            conn.close()


def test_startup_upgrade_repairs_legacy_payroll_adjustment_table() -> None:
    from api import server

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "legacy.sqlite"
        conn = get_conn(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE payroll_item_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payroll_run_id INTEGER NOT NULL,
                    payroll_item_id INTEGER NOT NULL,
                    employee_id INTEGER NOT NULL,
                    additional_earning REAL NOT NULL DEFAULT 0,
                    additional_earning_note TEXT,
                    other_deduction REAL NOT NULL DEFAULT 0,
                    other_deduction_note TEXT,
                    cash_advance_id INTEGER,
                    cash_advance_amount REAL NOT NULL DEFAULT 0,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_by TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(payroll_run_id, employee_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

        with (
            patch.object(server, "validate_runtime_environment", return_value=None),
            patch.object(server, "configured_db_path", return_value=db_path),
            patch.object(server, "ensure_schedule_schema", return_value=None),
            patch.object(server, "ensure_schedule_change_log_schema", return_value=None),
            patch.object(server, "ensure_workflow_schema", return_value=None),
            patch.object(server, "ensure_integration_schema", return_value=None),
            patch.object(server, "ensure_legacy_integration_writer_compatibility", return_value=None),
            patch.object(server, "reconcile_unlinked_split_shift_logs", return_value=None),
        ):
            server.initialize_runtime()

        conn = get_conn(db_path)
        try:
            columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_info(payroll_item_adjustments)"
                ).fetchall()
            }
            assert "cash_advance_note" in columns
            assert "version" in columns
        finally:
            conn.close()
