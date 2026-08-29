from __future__ import annotations

import unittest
from pathlib import Path


class DeployReadinessContractTests(unittest.TestCase):
    def test_normal_deploy_uses_activator_runtime_readiness(self) -> None:
        deploy = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        activator = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")

        self.assertIn('bash "$APP_ROOT/scripts/activate_staged_release.sh"', deploy)
        self.assertNotIn('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"', deploy)

        self.assertIn('READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-45}"', activator)
        self.assertIn("runtime_ready()", activator)
        self.assertIn("wait_runtime_ready()", activator)
        self.assertIn("wait_runtime_ready", activator)
        self.assertIn('curl -fsS "$API_HEALTH_URL"', activator)
        self.assertIn('curl -fsS "$WEB_HEALTH_URL"', activator)
        self.assertIn("systemctl status", activator)
        self.assertIn("journalctl -u", activator)
        self.assertNotIn("sleep 3", activator)


if __name__ == "__main__":
    unittest.main()
