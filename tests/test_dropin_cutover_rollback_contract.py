from __future__ import annotations

import unittest
from pathlib import Path


class DropInCutoverRollbackContractTests(unittest.TestCase):
    def test_wrapper_snapshots_and_restores_complete_pre_migration_state(self) -> None:
        source = Path("scripts/cutover_nonroot_runtime_clean.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('cp -a "$APP_ENV" "$MIGRATION_BACKUP/staff-payroll.env.before"', source)
        self.assertIn('cp -a "$unit_path" "$MIGRATION_BACKUP/$service.before"', source)
        self.assertIn('cp -a "$dropin_dir" "$MIGRATION_BACKUP/$service.d"', source)
        self.assertIn("restore_complete_pre_migration_state()", source)
        self.assertIn('cp -a "$MIGRATION_BACKUP/staff-payroll.env.before" "$APP_ENV"', source)
        self.assertIn('cp -a "$MIGRATION_BACKUP/$service.before" "$unit_path"', source)
        self.assertIn('cp -a "$MIGRATION_BACKUP/$service.d" "$dropin_dir"', source)
        self.assertIn('rm -f "$CURRENT_LINK"', source)
        self.assertIn('systemctl daemon-reload', source)
        self.assertIn('systemctl restart "$API_SERVICE"', source)
        self.assertIn('systemctl restart "$WEB_SERVICE"', source)
        self.assertIn('systemctl restart "$WORKER_SERVICE"', source)


if __name__ == "__main__":
    unittest.main()
