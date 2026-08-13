from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.backups import BackupVerificationError, create_backup_package, verify_backup
from core.db import get_conn, init_db, now_iso


class BackupPackageTests(unittest.TestCase):
    def test_package_contains_database_manifest_and_referenced_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "source.sqlite"
            upload_dir = root / "uploads"
            upload_dir.mkdir()
            attachment = upload_dir / "request.pdf"
            attachment.write_bytes(b"%PDF-\nunit test")

            conn = get_conn(db_path)
            try:
                init_db(conn)
                employee_id = int(
                    conn.execute(
                        """
                        INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
                        VALUES('UP-1','Upload User','Active',?,?)
                        """,
                        (now_iso(), now_iso()),
                    ).lastrowid
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shift_change_requests(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_id INTEGER NOT NULL,
                        attachment_path TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO shift_change_requests(employee_id, attachment_path) VALUES(?, ?)",
                    (employee_id, str(attachment)),
                )
                conn.commit()
            finally:
                conn.close()

            backup_dir = root / "backups"
            with patch.dict(
                os.environ,
                {
                    "STAFF_PAYROLL_BACKUP_DIR": str(backup_dir),
                    "STAFF_UPLOAD_DIR": str(upload_dir),
                    "STAFF_PAYROLL_BACKUP_KEY": "",
                },
            ):
                result = create_backup_package(db_path)

            package_path = Path(result["path"])
            self.assertTrue(package_path.exists())
            self.assertEqual(result["attachment_count"], 1)
            with zipfile.ZipFile(package_path) as archive:
                names = set(archive.namelist())
                self.assertIn("database/staff-payroll.sqlite", names)
                self.assertIn("uploads/request.pdf", names)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["attachment_count"], 1)
                self.assertEqual(manifest["missing_attachment_paths"], [])
                extracted_db = root / "extracted.sqlite"
                extracted_db.write_bytes(archive.read("database/staff-payroll.sqlite"))

            sqlite_conn = sqlite3.connect(str(extracted_db))
            try:
                self.assertEqual(sqlite_conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                sqlite_conn.close()

    def test_created_zip_package_can_be_verified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "source.sqlite"
            upload_dir = root / "uploads"
            upload_dir.mkdir()
            conn = get_conn(db_path)
            try:
                init_db(conn)
                conn.commit()
            finally:
                conn.close()
            backup_dir = root / "backups"
            with patch.dict(
                os.environ,
                {
                    "STAFF_PAYROLL_BACKUP_DIR": str(backup_dir),
                    "STAFF_UPLOAD_DIR": str(upload_dir),
                    "STAFF_PAYROLL_BACKUP_KEY": "",
                },
            ):
                result = create_backup_package(db_path)
                verified = verify_backup(Path(result["path"]))
            self.assertTrue(verified["ok"])
            self.assertGreaterEqual(verified["table_count"], 1)
            self.assertIn("manifest", verified)

    def test_corrupted_zip_package_raises_controlled_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corrupt = Path(temp_dir) / "staff-payroll-package-corrupt.zip"
            corrupt.write_bytes(b"this is not a zip")
            with self.assertRaises(BackupVerificationError) as err:
                verify_backup(corrupt)
            self.assertIn("corrupted", str(err.exception).lower())

    def test_corrupted_sqlite_backup_raises_controlled_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corrupt = Path(temp_dir) / "staff-payroll-corrupt.sqlite"
            corrupt.write_bytes(b"not sqlite")
            with self.assertRaises(BackupVerificationError) as err:
                verify_backup(corrupt)
            self.assertIn("sqlite", str(err.exception).lower())


if __name__ == "__main__":
    unittest.main()
