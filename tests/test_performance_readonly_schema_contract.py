from __future__ import annotations

import inspect
import sqlite3
import unittest

from api import performance_reviews, server


class PerformanceReadonlySchemaContractTests(unittest.TestCase):
    def test_startup_initializes_both_performance_schemas(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_performance_review_schema(conn)", source)
        self.assertIn("ensure_performance_logs_schema(conn)", source)

    def test_annual_review_get_does_not_initialize_or_commit_schema(self) -> None:
        source = inspect.getsource(performance_reviews.list_annual_reviews)
        self.assertNotIn("ensure_schema(conn)", source)
        self.assertNotIn("conn.commit()", source)

    def test_performance_logs_get_does_not_initialize_or_commit_schema(self) -> None:
        source = inspect.getsource(performance_reviews.list_performance_logs)
        self.assertNotIn("ensure_performance_logs_schema(conn)", source)
        self.assertNotIn("conn.commit()", source)

    def test_schema_initializers_create_required_tables_before_reads(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            performance_reviews.ensure_schema(conn)
            performance_reviews.ensure_performance_logs_schema(conn)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("annual_performance_reviews", tables)
            self.assertIn("performance_logs", tables)
        finally:
            conn.close()

    def test_write_handlers_keep_defensive_schema_checks(self) -> None:
        annual_write = inspect.getsource(performance_reviews.save_annual_review)
        log_write = inspect.getsource(performance_reviews.save_performance_log)
        self.assertIn("ensure_schema(conn)", annual_write)
        self.assertIn("ensure_performance_logs_schema(conn)", log_write)


if __name__ == "__main__":
    unittest.main()
