from __future__ import annotations

import unittest
from pathlib import Path


class DeployNpmAuditRetryContractTests(unittest.TestCase):
    def test_deploy_retries_production_npm_audit_without_failing_open(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        self.assertIn("run_npm_audit_with_retry()", source)
        self.assertIn("NPM_AUDIT_ATTEMPTS", source)
        self.assertIn("NPM_AUDIT_RETRY_DELAY_SECONDS", source)
        self.assertIn("return 1", source)
        self.assertIn("run_npm_audit_with_retry --omit=dev --audit-level=high", source)
        self.assertNotIn("npm audit --omit=dev --audit-level=high || true", source)

    def test_full_dev_tooling_audit_is_visible_but_non_blocking(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        self.assertIn("Running informational full npm audit (including dev tooling)", source)
        self.assertIn("if ! npm audit --audit-level=high; then", source)
        self.assertIn(
            "full npm audit reported development-tooling advisories; production dependency audit passed.",
            source,
        )
        self.assertNotIn("run_npm_audit_with_retry --audit-level=high", source)
        self.assertNotIn("npm audit --audit-level=high || true", source)


if __name__ == "__main__":
    unittest.main()
