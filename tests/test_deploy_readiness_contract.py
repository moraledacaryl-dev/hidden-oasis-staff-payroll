from __future__ import annotations

import unittest
from pathlib import Path


class DeployReadinessContractTests(unittest.TestCase):
    def test_normal_deploy_polls_runtime_readiness_instead_of_fixed_sleep(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        self.assertIn('READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-45}"', source)
        self.assertIn("runtime_ready()", source)
        self.assertIn("wait_runtime_ready()", source)
        self.assertIn("wait_runtime_ready", source)
        self.assertIn('curl -fsS "$API_HEALTH_URL"', source)
        self.assertIn('curl -fsS "$WEB_HEALTH_URL"', source)
        self.assertIn("runtime readiness timeout", source)
        self.assertIn("journalctl -u", source)
        self.assertNotIn("sleep 3", source)


if __name__ == "__main__":
    unittest.main()
