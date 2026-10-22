from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CashAdvanceReviewUiContractTests(unittest.TestCase):
    def test_approved_unissued_and_released_have_distinct_labels(self) -> None:
        page = (ROOT / "apps/web/app/cash-advances/page.tsx").read_text(encoding="utf-8")
        self.assertIn('"Approved · not issued"', page)
        self.assertIn('"Funds issued"', page)
        self.assertNotIn('status === "Approved" || status === "Released" ? "Active"', page)

    def test_filter_routes_reuse_existing_read_only_advance_data(self) -> None:
        page = (ROOT / "apps/web/app/cash-advances/page.tsx").read_text(encoding="utf-8")
        for key in ("awaiting", "outstanding", "closed"):
            self.assertIn(f'"/cash-advances?view={key}"', page)
        self.assertIn('selectedView === "awaiting" ? awaitingRelease', page)
        self.assertIn('selectedView === "outstanding" ? active', page)
        self.assertIn('selectedView === "closed" ? closed', page)
        self.assertIn('params?.review === "accounting"', page)

    def test_release_date_input_cannot_precede_advance_request(self) -> None:
        drawer = (ROOT / "apps/web/components/ConfirmCashAdvanceRelease.tsx").read_text(encoding="utf-8")
        page = (ROOT / "apps/web/app/cash-advances/page.tsx").read_text(encoding="utf-8")
        self.assertIn('min={advanceDate.slice(0, 10)}', drawer)
        self.assertIn('advanceDate={item.advance_date}', page)

    def test_browser_smoke_captures_new_filtered_views(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for key in ("awaiting", "outstanding", "closed"):
            self.assertIn(f'/cash-advances?view={key}', workflow)


if __name__ == "__main__":
    unittest.main()
