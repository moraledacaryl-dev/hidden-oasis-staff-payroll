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


if __name__ == "__main__":
    unittest.main()
