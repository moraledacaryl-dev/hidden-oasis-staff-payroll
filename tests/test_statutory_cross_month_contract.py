from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class StatutoryCrossMonthContractTests(unittest.TestCase):
    def test_calendar_month_segmenter_documents_boundary_cutoffs(self) -> None:
        source = (ROOT / "core" / "statutory_periods.py").read_text(encoding="utf-8")
        self.assertIn("calendar_month_segments", source)
        self.assertIn("callers must not classify the entire cutoff", source)

    def test_known_legacy_single_anchor_paths_remain_visible_until_migrated(self) -> None:
        """Fail loudly if a migration deletes the legacy signatures without replacing this guard.

        This test is intentionally temporary while the behavioral migration is developed on
        this branch.  It records the exact debt that the next commit must remove from both
        recomputation paths rather than allowing a one-path hotfix.
        """
        engine = (ROOT / "core" / "payroll_engine.py").read_text(encoding="utf-8")
        fractional = (ROOT / "core" / "payroll_fractional_leave.py").read_text(encoding="utf-8")
        boundary = (ROOT / "api" / "active_money_boundary_closure.py").read_text(encoding="utf-8")
        self.assertIn('get_month_previous_contribs(conn, int(emp["id"]), period_start)', engine)
        self.assertIn('get_month_previous_contribs(conn, int(emp["id"]), period_start)', fractional)
        self.assertIn('get_month_previous_contribs(conn, int(emp["id"]), period_start)', boundary)


if __name__ == "__main__":
    unittest.main()
