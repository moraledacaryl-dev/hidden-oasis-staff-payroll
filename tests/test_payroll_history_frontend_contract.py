from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PayrollHistoryFrontendContractTests(unittest.TestCase):
    def test_history_page_uses_server_side_paging_and_preserves_filters(self) -> None:
        ui = (ROOT / "apps/web/app/payroll/runs/page.tsx").read_text()
        self.assertIn("getPayrollRunHistory({", ui)
        self.assertIn("historyPageHref(history.page - 1)", ui)
        self.assertIn("historyPageHref(history.page + 1)", ui)
        self.assertIn('query.set("status", filters.status)', ui)
        self.assertIn('query.set("start", filters.start)', ui)
        self.assertIn('query.set("end", filters.end)', ui)
        self.assertIn('query.set("page", String(targetPage))', ui)
        self.assertIn("history.total", ui)
        self.assertNotIn("getPayrollRuns()", ui)

    def test_api_history_is_readonly_bounded_and_authenticated(self) -> None:
        api = (ROOT / "api/payroll_drafts.py").read_text()
        self.assertIn('@router.get("/payroll/runs/history")', api)
        self.assertIn("must_be_payroll_user(authorization, x_api_key)", api)
        self.assertIn("with db_conn(read_only=True) as conn", api)
        self.assertIn("LIMIT ? OFFSET ?", api)
        self.assertIn("page_size: int = Query(default=25, ge=1, le=100)", api)
        self.assertIn("COALESCE(superseded_by_run_id,0)<>0", api)

    def test_cutoff_uses_period_targeted_archive_without_losing_legacy_actions(self) -> None:
        cutoff = (ROOT / "apps/web/app/cutoff/page.tsx").read_text()
        self.assertIn("getPayrollRunHistory({ start: periodStart, end: periodEnd, pageSize: 100 })", cutoff)
        self.assertIn("const matchingTotal = history?.total || 0", cutoff)
        self.assertIn("Full history", cutoff)
        self.assertIn("<PayrollLifecycleButtons", cutoff)
        self.assertNotIn("getPayrollRuns()", cutoff)

    def test_browser_smoke_covers_history_filters(self) -> None:
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("/payroll/runs?page=2", ci)
        self.assertIn("/payroll/runs?start=2025-01-01", ci)


if __name__ == "__main__":
    unittest.main()
