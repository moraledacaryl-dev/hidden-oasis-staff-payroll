"""Contract: historical accounting handoff worklist remains observational."""
from pathlib import Path
import unittest


class CashAdvanceAccountingReviewQueueContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Path("apps/web/app/cash-advances/page.tsx").read_text(encoding="utf-8")
        cls.seed = Path("scripts/browser_smoke_seed.py").read_text(encoding="utf-8")
        cls.smoke = Path("apps/web/scripts/browser-smoke.mjs").read_text(encoding="utf-8")

    def test_queue_filters_only_active_manual_handoff_exceptions(self):
        page = self.page
        for state in ("missing_staff_outbox", "delivery_requires_review",
                      "outbox_status_unavailable"):
            self.assertIn(f'"{state}"', page)
        self.assertIn('repayment.source?.trim().toLowerCase() === "manual"', page)
        self.assertIn('handoffReviewStates.has(repayment.accounting_handoff_state || "")', page)
        self.assertNotIn('"delivered_posting_unverified",\n  "pending_delivery"', page)
        self.assertIn('const visibleAdvances = reviewOnly', page)
        self.assertIn('advances.filter((item) => affectedAdvanceIds.has(item.id))', page)

    def test_queue_aggregates_centavo_amount_and_keeps_other_advances_visible(self):
        self.assertIn('Math.round(Number(repayment.amount || 0) * 100)', self.page)
        self.assertIn('peso(exceptionAmountCentavos / 100)', self.page)
        self.assertIn('href="/cash-advances?review=accounting"', self.page)
        self.assertIn('href="/cash-advances"', self.page)
        self.assertIn("not\n          confirmation of an unposted Accounting receipt or missing funds", self.page)
        self.assertIn("fully paid advance does not confirm cash posting", self.page)
        self.assertNotIn("Accounting posted", self.page)
        self.assertNotIn("replayOutbox", self.page)
        self.assertNotIn('method="POST"', self.page)

    def test_browser_smoke_captures_exception_queue_on_all_viewports(self):
        self.assertIn('"/cash-advances?review=accounting"', self.smoke)
        ci_workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('"/cash-advances?review=accounting"', ci_workflow)
        self.assertIn("accountingQueueCheck", self.smoke)
        self.assertIn("Manual repayment requires Staff Accounting handoff review", self.smoke)
        self.assertIn("Page.captureScreenshot", self.smoke)
        self.assertIn("exception_advance_id", self.seed)
        self.assertIn("'Fully Paid'", self.seed)
        self.assertIn("'Manual', 'Cash', 'Cash'", self.seed)


if __name__ == "__main__":
    unittest.main()
