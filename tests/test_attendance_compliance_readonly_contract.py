from __future__ import annotations

import inspect
import sqlite3
import unittest

from api import attendance_compliance, attendance_compliance_runtime, server


class AttendanceComplianceReadonlyContractTests(unittest.TestCase):
    def test_startup_owns_attendance_compliance_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_attendance_compliance_schema(conn)", source)

    def test_runtime_get_never_initializes_or_commits_schema(self) -> None:
        source = inspect.getsource(attendance_compliance_runtime.attendance_compliance_readonly)
        self.assertNotIn("ensure_schema(conn)", source)
        self.assertNotIn("conn.commit()", source)
        self.assertNotIn("ALTER TABLE", source)
        self.assertNotIn("CREATE TABLE", source)

    def test_runtime_router_preserves_write_handler(self) -> None:
        routes = [
            (getattr(route, "path", ""), {str(m).upper() for m in getattr(route, "methods", set())})
            for route in attendance_compliance_runtime.router.routes
        ]
        self.assertIn(("/api/v1/attendance/compliance", {"GET"}), routes)
        self.assertIn(("/api/v1/attendance/memos", {"POST"}), routes)

    def test_schema_initializer_upgrades_legacy_time_logs_before_reads(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE time_logs (id INTEGER PRIMARY KEY)")
            attendance_compliance.ensure_schema(conn)
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(time_logs)").fetchall()
            }
            self.assertTrue({"notice_given_at", "notice_timing", "evidence_ref"} <= columns)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("attendance_memos", tables)
        finally:
            conn.close()

    def test_legacy_write_handler_keeps_defensive_schema_check(self) -> None:
        source = inspect.getsource(attendance_compliance.create_attendance_memo)
        self.assertIn("ensure_schema(conn)", source)
        self.assertIn("conn.commit()", source)


if __name__ == "__main__":
    unittest.main()
