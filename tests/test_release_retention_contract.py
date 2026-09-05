from __future__ import annotations

import unittest
from pathlib import Path


class ReleaseRetentionContractTests(unittest.TestCase):
    def test_release_pruner_preserves_current_and_minimum_rollback_depth(self) -> None:
        source = Path("scripts/prune_runtime_releases.sh").read_text(encoding="utf-8")

        self.assertIn('KEEP_COUNT="${STAFF_PAYROLL_RELEASE_KEEP_COUNT:-3}"', source)
        self.assertIn('(( KEEP_COUNT >= 2 ))', source)
        self.assertIn('current_release="$(readlink -f "$CURRENT_LINK"', source)
        self.assertIn('keep["$current_release"]=1', source)
        self.assertIn('rm -rf --one-file-system "$release"', source)
        self.assertIn('[[ "$release" == "$RELEASES_DIR"/* ]]', source)

    def test_release_pruner_is_not_allowed_to_touch_state_or_backups(self) -> None:
        source = Path("scripts/prune_runtime_releases.sh").read_text(encoding="utf-8")

        self.assertNotIn("/var/lib/hiddenoasis", source)
        self.assertNotIn("/var/backups", source)
        self.assertNotIn("STAFF_PAYROLL_DB_PATH", source)
        self.assertNotIn("STAFF_UPLOAD_DIR", source)

    def test_safe_deploy_wrapper_prunes_only_after_canonical_deploy_success(self) -> None:
        source = Path("scripts/deploy_production_retained.sh").read_text(encoding="utf-8")

        deploy = 'bash "$APP_ROOT/scripts/deploy_production.sh"'
        prune = 'bash "$APP_ROOT/scripts/prune_runtime_releases.sh"'
        self.assertEqual(source.count(deploy), 1)
        self.assertEqual(source.count(prune), 1)
        self.assertLess(source.index(deploy), source.index(prune))
        self.assertIn("set -euo pipefail", source)

    def test_retention_failure_warns_without_falsely_failing_live_deploy(self) -> None:
        source = Path("scripts/deploy_production_retained.sh").read_text(encoding="utf-8")

        self.assertIn('if ! bash "$APP_ROOT/scripts/prune_runtime_releases.sh"; then', source)
        self.assertIn('WARNING: deployment succeeded, but runtime release retention cleanup failed.', source)
        self.assertIn('Deployment and release retention workflow complete.', source)


if __name__ == "__main__":
    unittest.main()
