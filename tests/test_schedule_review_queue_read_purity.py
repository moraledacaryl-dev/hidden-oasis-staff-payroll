from __future__ import annotations

import inspect
import unittest

from api import schedule_review_queue, schedules


class ScheduleReviewQueueReadPurityTests(unittest.TestCase):
    def test_schedule_items_does_not_initialize_schema(self) -> None:
        source = inspect.getsource(schedule_review_queue.schedule_items)
        self.assertNotIn("ensure_schedule_review_columns", source)

    def test_review_decision_keeps_defensive_schema_initialization(self) -> None:
        source = inspect.getsource(schedule_review_queue.decide_review_item)
        self.assertIn("ensure_schedule_review_columns(conn)", source)

    def test_schedule_startup_schema_owns_review_columns(self) -> None:
        source = inspect.getsource(schedules.ensure_schema)
        self.assertIn("ensure_schedule_review_columns(conn)", source)


if __name__ == "__main__":
    unittest.main()
