from __future__ import annotations

import unittest
from pathlib import Path


class DeployRollbackContractTests(unittest.TestCase):
    def test_production_deploy_delegates_cutover_and_rollback(self) -> None:
        deploy = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        activator = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")

        self.assertIn('bash "$APP_ROOT/scripts/activate_staged_release.sh"', deploy)
        self.assertNotIn('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"', deploy)
        self.assertNotIn("rollback_runtime()", deploy)

        self.assertIn("rollback() {", activator)
        self.assertIn('mv -Tf "$RUNTIME_BASE/.current.rollback" "$CURRENT_LINK"', activator)
        self.assertIn("if wait_runtime_ready; then", activator)
        self.assertIn("Rollback runtime readiness restored.", activator)
        self.assertIn("rollback failed to restore canonical runtime readiness", activator)
        self.assertIn("rollback 1", activator)


if __name__ == "__main__":
    unittest.main()
