from __future__ import annotations

import unittest
from pathlib import Path


class ReadinessReportingContractTests(unittest.TestCase):
    """Ensure owner control panels cannot present truncated history as totals."""

    def test_launch_uses_complete_history_and_defines_recovery_caveat(self) -> None:
        source = Path("apps/web/app/launch/page.tsx").read_text(encoding="utf-8")
        self.assertIn("getPayrollRunHistory({ page: 1, pageSize: 1 })", source)
        self.assertIn("history ? history.total", source)
        self.assertNotIn("getPayrollRuns()", source)
        self.assertIn("backup_max_age_hours", source)
        self.assertIn("offsite_backup_configuration_status", source)
        self.assertIn("release_verified", source)
        self.assertIn("deployment_space_ok", source)
        self.assertIn("separate verification", source.lower())
        self.assertNotIn('label={ready ? "ready"', source)

    def test_controls_uses_untruncated_totals_and_current_paid_status(self) -> None:
        source = Path("apps/web/app/controls/page.tsx").read_text(encoding="utf-8")
        self.assertIn("getPayrollRunHistory({ page: 1, pageSize: 4 })", source)
        self.assertIn("history.total", source)
        self.assertIn("history.summary.paid", source)
        self.assertIn("history.summary.superseded", source)
        self.assertNotIn("getPayrollRuns()", source)

    def test_health_does_not_conflate_offsite_settings_and_verified_copy(self) -> None:
        source = Path("api/production_health.py").read_text(encoding="utf-8")
        self.assertIn('"offsite_backup_configuration_status": offsite_status', source)
        self.assertIn('"offsite_backup_copy_verified": False', source)
        self.assertIn('"backup_max_age_hours": backup_age_limit_hours()', source)
        self.assertNotIn('bool(os.getenv("STAFF_PAYROLL_OFFSITE_BACKUP_DIR"))', source)


if __name__ == "__main__":
    unittest.main()
