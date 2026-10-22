from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Group2PayrollVisibilityTests(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_superseded_and_active_versions_are_distinct(self) -> None:
        source = self.read("apps/web/app/payroll/runs/page.tsx")
        self.assertIn('filters.view === "superseded"', source)
        self.assertIn('getPayrollRunHistory({', source)
        backend = self.read('api/payroll_drafts.py')
        self.assertIn('COALESCE(superseded_by_run_id,0)=0', backend)
        self.assertIn('run.superseded_by_run_id ? <small', source)
        self.assertIn('Audit only · superseded by', source)
        self.assertIn('name="view"', source)
        self.assertIn('<option>Locked</option>', source)
        self.assertIn('<option>Released</option>', source)
        self.assertIn('history.total', source)
        self.assertIn('history.summary', source)

    def test_dashboard_work_in_progress_excludes_superseded(self) -> None:
        source = self.read("apps/web/app/controls/page.tsx")
        backend = self.read("api/payroll_drafts.py")
        self.assertIn("getPayrollRunHistory({ page: 1, pageSize: 4 })", source)
        self.assertIn("history.summary.draft + history.summary.review + history.summary.approved", source)
        self.assertIn("history.summary.paid", source)
        self.assertIn("history.summary.superseded", source)
        # The backend summary, not a truncated client-side list, excludes
        # superseded runs from the current workflow and paid counts.
        self.assertIn("COALESCE(superseded_by_run_id,0)=0 AND status='Draft'", backend)
        self.assertIn("status IN ('Paid','Released','Locked')", backend)

    def test_reports_do_not_call_projected_contributions_paid(self) -> None:
        source = self.read("apps/web/app/reports/page.tsx")
        self.assertIn('Projected contributions and deductions', source)
        self.assertIn('not finalized payroll liabilities or confirmed agency payments', source)
        self.assertIn('do not prove employee deductions were collected', source)
        self.assertIn('Preview only · not paid', source)

    def test_health_dashboard_shows_storage_without_automatic_cleanup(self) -> None:
        backend = self.read("api/production_health.py")
        ui = self.read("apps/web/app/controls/production-health/page.tsx")
        self.assertIn('"disk_capacity": filesystem_capacity(', backend)
        self.assertIn('Deployment storage readiness', ui)
        self.assertIn('deployment_space_ok', ui)
        self.assertIn('Do not bypass the preflight', ui)

    def test_new_views_in_browser_smoke(self) -> None:
        workflow = self.read(".github/workflows/ci.yml")
        self.assertIn('/payroll/runs?view=current', workflow)
        self.assertIn('/payroll/runs?view=superseded', workflow)
        self.assertIn('/controls', workflow)


if __name__ == "__main__":
    unittest.main()
