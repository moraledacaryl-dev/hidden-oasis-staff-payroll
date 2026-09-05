from __future__ import annotations

import inspect
import unittest

import api.schedule_canonical_runtime as schedule_runtime
import api.server as server


class ScheduleWeekReadonlyContractTests(unittest.TestCase):
    def test_weekly_schedule_get_does_not_initialize_schema(self) -> None:
        source = inspect.getsource(schedule_runtime.schedule_week)
        self.assertNotIn("ensure_schema", source)
        self.assertNotIn("commit(", source)
        self.assertNotIn("ALTER TABLE", source.upper())
        self.assertNotIn("CREATE TABLE", source.upper())
        self.assertNotIn("CREATE INDEX", source.upper())

    def test_startup_owns_schedule_schema_initialization(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_schedule_schema(conn)", source)


if __name__ == "__main__":
    unittest.main()
