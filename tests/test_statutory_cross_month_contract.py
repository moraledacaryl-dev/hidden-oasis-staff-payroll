from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class StatutoryCrossMonthContractTests(unittest.TestCase):
    def test_calendar_month_segmenter_documents_boundary_cutoffs(self) -> None:
        source = (ROOT / "core" / "statutory_periods.py").read_text(encoding="utf-8")
        self.assertIn("calendar_month_segments", source)
        self.assertIn("callers must not classify the entire cutoff", source)

    def test_supersession_safe_history_is_available_for_migration(self) -> None:
        source = (ROOT / "core" / "statutory_history.py").read_text(encoding="utf-8")
        self.assertIn("superseded_by_run_id IS NULL", source)
        self.assertNotIn('"Draft",', source)
        self.assertIn("Draft runs are deliberately excluded", source)


if __name__ == "__main__":
    unittest.main()
