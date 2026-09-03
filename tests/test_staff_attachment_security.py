from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import api.server as server
from api.staff_attachment_security import (
    _resolved_attachment_path,
    _safe_download_name,
    ensure_attachment_schema,
    router as staff_attachment_router,
)


class StaffAttachmentSecurityTests(unittest.TestCase):
    def test_attachment_schema_adds_security_metadata_to_legacy_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE shift_change_requests (
                id INTEGER PRIMARY KEY,
                employee_id INTEGER NOT NULL,
                shift_id INTEGER NOT NULL,
                request_type TEXT NOT NULL,
                original_date TEXT NOT NULL,
                original_start_time TEXT NOT NULL,
                original_end_time TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                submitted_by_user_id INTEGER NOT NULL,
                submitted_at TEXT NOT NULL,
                attachment_path TEXT
            );
            CREATE TABLE shift_change_request_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                actor_user_id INTEGER,
                actor_employee_id INTEGER,
                note TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        ensure_attachment_schema(conn)
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(shift_change_requests)")}
        self.assertTrue(
            {
                "attachment_original_name",
                "attachment_sha256",
                "attachment_size_bytes",
                "attachment_validation_status",
                "attachment_uploaded_at",
            }.issubset(columns)
        )

    def test_download_refuses_database_path_outside_managed_upload_root(self) -> None:
        with tempfile.TemporaryDirectory() as upload_dir, tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "secret.pdf"
            outside.write_bytes(b"%PDF-1.4")
            with patch.dict(os.environ, {"STAFF_UPLOAD_DIR": upload_dir}):
                with self.assertRaises(HTTPException) as raised:
                    _resolved_attachment_path(str(outside))
            self.assertEqual(raised.exception.status_code, 409)

    def test_download_accepts_existing_file_inside_managed_upload_root(self) -> None:
        with tempfile.TemporaryDirectory() as upload_dir:
            attachment = Path(upload_dir) / "safe.pdf"
            attachment.write_bytes(b"%PDF-1.4")
            with patch.dict(os.environ, {"STAFF_UPLOAD_DIR": upload_dir}):
                resolved = _resolved_attachment_path(str(attachment))
            self.assertEqual(resolved, attachment.resolve())

    def test_download_filename_strips_path_and_unsafe_characters(self) -> None:
        self.assertEqual(
            _safe_download_name("../../employee <private>.pdf", 42, ".pdf"),
            "employee _private_.pdf",
        )
        self.assertEqual(
            _safe_download_name("evidence.exe", 42, ".pdf"),
            "evidence.pdf",
        )

    def test_canonical_routes_replace_legacy_upload_and_expose_authorized_downloads(self) -> None:
        paths = server.app.openapi()["paths"]
        staff_path = "/api/v1/me/shift-change-requests/{request_id}/attachment"
        reviewer_path = "/api/v1/shift-change-requests/{request_id}/attachment"
        self.assertIn(staff_path, paths)
        self.assertEqual(sorted(paths[staff_path]), ["get", "post"])
        self.assertIn(reviewer_path, paths)
        self.assertEqual(sorted(paths[reviewer_path]), ["get"])

        hardened_posts = [
            route
            for route in staff_attachment_router.routes
            if getattr(route, "path", None) == staff_path
            and "POST" in (getattr(route, "methods", set()) or set())
        ]
        self.assertEqual(len(hardened_posts), 1)
        endpoint = getattr(hardened_posts[0], "endpoint", None)
        self.assertEqual(getattr(endpoint, "__module__", ""), "api.staff_attachment_security")
        self.assertIn(
            (staff_path, "POST"),
            server.STAFF_SELF_SERVICE_EXCLUDED_ROUTES,
        )


if __name__ == "__main__":
    unittest.main()
