from __future__ import annotations

import inspect
import sqlite3
import unittest

import api.schedule_rest_days as rest_days
import api.server as server


class RestDayReadonlyContractTests(unittest.TestCase):
    def test_list_rest_days_does_not_initialize_schema_or_commit(self) -> None:
        source = inspect.getsource(rest_days.list_rest_days)
        self.assertNotIn("ensure_schema(conn)", source)
        self.assertNotIn("conn.commit()", source)
        self.assertNotIn("CREATE TABLE", source)
        self.assertNotIn("ALTER TABLE", source)

    def test_save_rest_day_keeps_defensive_schema_and_stale_actual_cleanup(self) -> None:
        source = inspect.getsource(rest_days.save_rest_day)
        self.assertIn("ensure_schema(conn)", source)
        self.assertIn("DELETE FROM time_logs", source)
        self.assertIn("clear_actual_for_rest_day", source)
        self.assertIn("conn.commit()", source)

    def test_startup_owns_rest_day_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_rest_day_schema(conn)", source)

    def test_rest_day_schema_builds_on_fresh_connection(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            rest_days.ensure_schema(conn)
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_day_markers'"
            ).fetchone()
            index = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_schedule_day_markers_week'"
            ).fetchone()
            self.assertEqual(("schedule_day_markers",), table)
            self.assertEqual(("idx_schedule_day_markers_week",), index)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
