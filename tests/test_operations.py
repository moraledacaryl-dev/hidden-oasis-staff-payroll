from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.employees import EmployeeEditorPayload, edit_employee
from api.users import (
    ChangeUserRoleRequest,
    ToggleUserActiveRequest,
    set_user_active,
    set_user_role,
)
from core.backups import create_backup, verify_backup
from core.db import fetchall, fetchone, get_conn, init_db, now_iso
from core.login_security import (
    clear_login_failures,
    lock_remaining_seconds,
    record_login_failure,
)
from api.server import initialize_runtime
from api.schedules import schedule_employees


class DatabaseOperationsTests(unittest.TestCase):
    def test_general_manager_employee_edit_preserves_payroll_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "employees.sqlite"
            conn = get_conn(db_path)
            try:
                init_db(conn)
                employee_id = int(
                    conn.execute(
                        """
                        INSERT INTO employees(
                            employee_code, full_name, department, position, status,
                            benefits_sss, benefits_philhealth, benefits_pagibig, benefits_tax,
                            created_at, updated_at
                        ) VALUES('GM-1','Managed Person','Front Office','Associate','Active',1,1,1,1,?,?)
                        """,
                        (now_iso(), now_iso()),
                    ).lastrowid
                )
                conn.commit()
            finally:
                conn.close()

            manager = {
                "id": 2,
                "display_name": "General Manager",
                "role_key": "supervisor",
            }
            payload = EmployeeEditorPayload(
                employee_code="GM-1",
                full_name="Managed Person",
                department_name="Operations",
                position="Senior Associate",
                employment_type="Regular",
                status="Active",
            )
            with patch.dict(os.environ, {"STAFF_PAYROLL_DB_PATH": str(db_path)}):
                edit_employee(employee_id, payload, user=manager)

                with self.assertRaises(HTTPException) as protected:
                    edit_employee(
                        employee_id,
                        payload.model_copy(update={"benefits_sss": 0}),
                        user=manager,
                    )
            self.assertEqual(protected.exception.status_code, 403)

            conn = get_conn(db_path)
            try:
                employee = fetchone(
                    conn,
                    """
                    SELECT department, position, benefits_sss, benefits_philhealth,
                           benefits_pagibig, benefits_tax
                    FROM employees WHERE id=?
                    """,
                    (employee_id,),
                )
            finally:
                conn.close()
            self.assertEqual(employee["department"], "Operations")
            self.assertEqual(employee["position"], "Senior Associate")
            self.assertEqual(
                (
                    employee["benefits_sss"],
                    employee["benefits_philhealth"],
                    employee["benefits_pagibig"],
                    employee["benefits_tax"],
                ),
                (1, 1, 1, 1),
            )

    def test_schedule_employee_list_excludes_inactive_status_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "employees.sqlite"
            conn = get_conn(db_path)
            try:
                init_db(conn)
                conn.execute(
                    """
                    INSERT INTO employees(
                        employee_code, full_name, status, created_at, updated_at
                    ) VALUES
                      ('A-1','Active Person','Active',?,?),
                      ('I-1','Inactive Person','Inactive',?,?)
                    """,
                    (now_iso(), now_iso(), now_iso(), now_iso()),
                )
                conn.commit()
            finally:
                conn.close()
            with (
                patch("api.schedules.DB_PATH", db_path),
                patch(
                    "api.schedules.require_schedule_viewer",
                    return_value={"role_key": "supervisor"},
                ),
            ):
                result = schedule_employees(authorization=None, x_api_key=None)
            self.assertEqual(
                [item["full_name"] for item in result["items"]],
                ["Active Person"],
            )

    def test_final_owner_cannot_be_deactivated_or_demoted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "owners.sqlite"
            conn = get_conn(db_path)
            try:
                init_db(conn)
                owner_id = int(
                    conn.execute(
                        """
                        INSERT INTO app_users(display_name, role, active, session_version, created_at)
                        VALUES('Owner', 'Owner', 1, 1, ?)
                        """,
                        (now_iso(),),
                    ).lastrowid
                )
                conn.commit()
            finally:
                conn.close()
            owner = {"id": owner_id, "display_name": "Owner", "role_key": "owner"}
            with (
                patch("api.users.DB_PATH", db_path),
                patch("api.users.require_owner", return_value=owner),
            ):
                with self.assertRaises(HTTPException) as deactivate:
                    set_user_active(
                        owner_id,
                        ToggleUserActiveRequest(active=False),
                        authorization=None,
                        x_api_key=None,
                    )
                self.assertEqual(deactivate.exception.status_code, 409)
                with self.assertRaises(HTTPException) as demote:
                    set_user_role(
                        owner_id,
                        ChangeUserRoleRequest(role="Staff"),
                        authorization=None,
                        x_api_key=None,
                    )
                self.assertEqual(demote.exception.status_code, 409)

    def test_startup_creates_operational_safety_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "startup.sqlite"
            with patch.dict(
                os.environ,
                {
                    "STAFF_PAYROLL_DB_PATH": str(db_path),
                    "STAFF_PAYROLL_ENV": "development",
                },
            ):
                initialize_runtime()
            conn = get_conn(db_path)
            try:
                names = {
                    str(row["name"])
                    for row in fetchall(
                        conn,
                        """
                        SELECT name FROM sqlite_master
                        WHERE type='table' AND name IN (
                            'schedule_change_logs',
                            'legacy_schedule_ignores',
                            'payroll_revision_change_links'
                        )
                        """,
                    )
                }
            finally:
                conn.close()
            self.assertEqual(
                names,
                {
                    "schedule_change_logs",
                    "legacy_schedule_ignores",
                    "payroll_revision_change_links",
                },
            )

    def test_file_database_uses_wal_and_all_migrations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "staff.sqlite"
            conn = get_conn(db_path)
            try:
                init_db(conn)
                journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
                busy_timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
                versions = [
                    int(row["version"])
                    for row in fetchall(conn, "SELECT version FROM schema_migrations ORDER BY version")
                ]
                user_columns = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(app_users)").fetchall()
                }
                self.assertEqual(journal_mode, "wal")
                self.assertGreaterEqual(busy_timeout, 1000)
                self.assertEqual(versions, [1, 2, 3, 4, 5])
                self.assertTrue(
                    {"session_version", "mfa_secret", "mfa_enabled"}.issubset(user_columns)
                )
                employee_columns = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(employees)").fetchall()
                }
                self.assertTrue(
                    {"default_shift_start", "default_shift_end"}.issubset(employee_columns)
                )
                self.assertEqual(
                    int(fetchone(conn, "SELECT COUNT(*) AS c FROM app_users")["c"]),
                    0,
                )
                self.assertEqual(
                    int(fetchone(conn, "SELECT COUNT(*) AS c FROM employees")["c"]),
                    0,
                )
            finally:
                conn.close()

    def test_login_failures_escalate_and_clear(self):
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            with patch.dict(os.environ, {"STAFF_PAYROLL_LOGIN_FAILURE_LIMIT": "3"}):
                self.assertEqual(record_login_failure(conn, "Owner", "127.0.0.1"), 0)
                self.assertEqual(record_login_failure(conn, " owner ", "127.0.0.1"), 0)
                self.assertEqual(record_login_failure(conn, "OWNER", "127.0.0.1"), 60)
                self.assertGreater(lock_remaining_seconds(conn, "owner", "127.0.0.1"), 0)
                clear_login_failures(conn, "Owner", "127.0.0.1")
                self.assertEqual(lock_remaining_seconds(conn, "owner", "127.0.0.1"), 0)
        finally:
            conn.close()


class BackupTests(unittest.TestCase):
    def _database(self, directory: str) -> Path:
        db_path = Path(directory) / "source.sqlite"
        conn = get_conn(db_path)
        try:
            init_db(conn)
            conn.execute(
                """
                INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
                VALUES('B-1','Backup User','Active',?,?)
                """,
                (now_iso(), now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
        return db_path

    def test_plain_backup_is_verified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._database(temp_dir)
            backup_dir = Path(temp_dir) / "backups"
            with patch.dict(
                os.environ,
                {
                    "STAFF_PAYROLL_BACKUP_DIR": str(backup_dir),
                    "STAFF_PAYROLL_BACKUP_KEY": "",
                },
            ):
                item = create_backup(db_path)
                result = verify_backup(Path(item["path"]))
            self.assertFalse(item["encrypted"])
            self.assertTrue(result["ok"])
            self.assertGreater(result["table_count"], 0)

    def test_encrypted_backup_requires_and_uses_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._database(temp_dir)
            backup_dir = Path(temp_dir) / "encrypted"
            environment = {
                "STAFF_PAYROLL_BACKUP_DIR": str(backup_dir),
                "STAFF_PAYROLL_BACKUP_KEY": "test-backup-secret",
            }
            with patch.dict(os.environ, environment):
                item = create_backup(db_path)
                result = verify_backup(Path(item["path"]))
            self.assertTrue(item["encrypted"])
            self.assertTrue(str(item["name"]).endswith(".fernet"))
            self.assertTrue(result["ok"])
            with patch.dict(
                os.environ,
                {
                    "STAFF_PAYROLL_BACKUP_DIR": str(backup_dir),
                    "STAFF_PAYROLL_BACKUP_KEY": "wrong-key",
                },
            ):
                with self.assertRaisesRegex(RuntimeError, "decryption failed"):
                    verify_backup(Path(item["path"]))


if __name__ == "__main__":
    unittest.main()
