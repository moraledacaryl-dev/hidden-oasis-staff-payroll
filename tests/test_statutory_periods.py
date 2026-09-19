from __future__ import annotations

import unittest
from datetime import date

from core.statutory_periods import calendar_month_segments


class StatutoryPeriodTests(unittest.TestCase):
    def test_same_month_cutoff_remains_one_segment(self) -> None:
        segments = calendar_month_segments("2026-07-16", "2026-07-31")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].start, date(2026, 7, 16))
        self.assertEqual(segments[0].end, date(2026, 7, 31))
        self.assertTrue(segments[0].is_month_closing_segment)

    def test_august_31_to_september_14_is_split_at_month_end(self) -> None:
        segments = calendar_month_segments("2026-08-31", "2026-09-14")
        self.assertEqual(
            [(segment.start, segment.end) for segment in segments],
            [
                (date(2026, 8, 31), date(2026, 8, 31)),
                (date(2026, 9, 1), date(2026, 9, 14)),
            ],
        )
        self.assertTrue(segments[0].is_month_closing_segment)
        self.assertTrue(segments[1].is_month_opening_segment)

    def test_september_30_to_october_14_is_split_at_month_end(self) -> None:
        segments = calendar_month_segments("2026-09-30", "2026-10-14")
        self.assertEqual(
            [(segment.start, segment.end) for segment in segments],
            [
                (date(2026, 9, 30), date(2026, 9, 30)),
                (date(2026, 10, 1), date(2026, 10, 14)),
            ],
        )

    def test_rejects_reversed_period(self) -> None:
        with self.assertRaises(ValueError):
            calendar_month_segments("2026-09-14", "2026-08-31")


if __name__ == "__main__":
    unittest.main()
