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

    def test_production_deploy_prunes_only_after_acceptance_checks(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")

        prune = 'bash "$APP_ROOT/scripts/prune_runtime_releases.sh"'
        self.assertEqual(source.count(prune), 1)
        prune_index = source.index(prune)
        self.assertLess(source.index('bash "$APP_ROOT/scripts/activate_staged_release.sh"'), prune_index)
        self.assertLess(source.index('verify_listener_owner "$WEB_SERVICE" 3001'), prune_index)
        self.assertLess(source.index('curl -fsS "$API_HEALTH_URL" >/dev/null'), prune_index)
        self.assertLess(source.index('curl -fsS "$WEB_HEALTH_URL" >/dev/null'), prune_index)
        self.assertLess(source.index('recent worker warning-level journal entries detected'), prune_index)

    def test_prune_failure_warns_without_falsely_failing_live_deploy(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")

        self.assertIn('if ! bash "$APP_ROOT/scripts/prune_runtime_releases.sh"; then', source)
        self.assertIn('WARNING: deployment succeeded, but runtime release retention cleanup failed.', source)
        self.assertGreater(
            source.index('Deployment completed successfully through canonical staged activator.'),
            source.index('WARNING: deployment succeeded, but runtime release retention cleanup failed.'),
        )


if __name__ == "__main__":
    unittest.main()
