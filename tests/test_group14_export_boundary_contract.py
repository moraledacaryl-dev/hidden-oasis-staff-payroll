from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


class Group14ExportBoundaryTests(unittest.TestCase):
    """Regression gates for access-controlled downloadable employee data."""

    def test_payroll_export_requires_authenticated_payroll_role(self) -> None:
        route = (WEB / "app/api/payroll/runs/[id]/export/route.ts").read_text()
        self.assertIn("await currentSession()", route)
        self.assertIn('if (!session) return new Response("Authentication required."', route)
        self.assertIn('["owner", "payroll"].includes(session.role_key)', route)
        self.assertIn('status: 403', route)
        self.assertIn("Number.isSafeInteger(runId)", route)
        self.assertIn('"items", "summary", "corrections"', route)
        self.assertLess(route.index('await currentSession()'), route.index("await getPayrollRunReview(runId)"))
        self.assertIn('const csv = csvDocument(', route)
        self.assertIn('"Cache-Control": "private, no-store"', route)
        self.assertIn('"X-Content-Type-Options": "nosniff"', route)

        # Backend permissions remain authoritative even if the web boundary
        # is accidentally bypassed or an API request is crafted directly.
        api = (ROOT / "api/payroll_service.py").read_text()
        self.assertIn('user["role_key"] not in {"owner", "payroll"}', api)
        self.assertIn("must_be_payroll_user(authorization, x_api_key)", api)

    def test_attendance_download_rejects_non_management_roles(self) -> None:
        route = (WEB / "app/api/attendance-template/download/route.ts").read_text()
        self.assertIn("await currentSession()", route)
        self.assertIn('["owner", "payroll", "supervisor"].includes(session.role_key)', route)
        self.assertIn('status: 401', route)
        self.assertIn('status: 403', route)
        self.assertLess(route.index("await currentSession()"), route.index("await loadEmployees()"))
        self.assertIn('csvCell', route)
        self.assertIn('"Cache-Control": "private, no-store"', route)
        self.assertIn('"X-Content-Type-Options": "nosniff"', route)

        backend = (ROOT / "api/schedules.py").read_text()
        self.assertIn('user.get("role_key") not in {"owner", "payroll", "supervisor"}', backend)

    def test_executable_formula_injection_tests_are_required_by_ci(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        package = (WEB / "package.json").read_text()
        self.assertIn("Test spreadsheet export safety", workflow)
        self.assertIn("npm run test:security", workflow)
        self.assertIn('"test:security": "node --test scripts/test-csv-security.mjs"', package)
        for route in (
            "app/api/attendance-template/download/route.ts",
            "app/api/payroll/runs/[id]/export/route.ts",
        ):
            self.assertIn('@/lib/csv-security.mjs', (WEB / route).read_text())

    def test_sensitive_downloads_do_not_inline_render(self) -> None:
        route = (WEB / "app/api/payroll/runs/[id]/export/route.ts").read_text()
        self.assertIn('attachment; filename=', route)
        route = (WEB / "app/api/attendance-template/download/route.ts").read_text()
        self.assertIn('attachment; filename=', route)


if __name__ == "__main__":
    unittest.main()
