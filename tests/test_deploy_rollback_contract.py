from __future__ import annotations

import unittest
from pathlib import Path


class DeployRollbackContractTests(unittest.TestCase):
    def test_fatal_post_activation_failure_invokes_rollback_explicitly(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        self.assertIn('if [[ "$ACTIVATED" == "1" && -n "$PREVIOUS_RELEASE" ]]; then', source)
        self.assertIn("rollback_runtime 1", source)
        self.assertIn("ACTIVATED=0", source)
        self.assertIn('quiesce_runtime || true', source)
        self.assertIn('mv -Tf "$RUNTIME_BASE/.current.rollback" "$CURRENT_LINK"', source)


if __name__ == "__main__":
    unittest.main()
