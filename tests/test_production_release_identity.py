from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.production_health import release_state


class ProductionReleaseIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.runtime = self.root / "runtime"
        self.releases = self.runtime / "releases"
        self.releases.mkdir(parents=True)
        self.marker = self.root / "deployed-sha"
        self.sha = "a" * 40
        self.active = self.releases / self.sha
        self.active.mkdir()
        (self.runtime / "current").symlink_to(self.active, target_is_directory=True)
        env = patch.dict(os.environ, {
            "STAFF_PAYROLL_RUNTIME_BASE": str(self.runtime),
            "STAFF_PAYROLL_DEPLOY_STATE_FILE": str(self.marker),
        })
        env.start()
        self.addCleanup(env.stop)

    def test_matching_marker_and_active_release_is_verified(self) -> None:
        self.marker.write_text(self.sha + "\n", encoding="utf-8")
        state = release_state()
        self.assertTrue(state["release_verified"])
        self.assertEqual(state["active_release_sha"], self.sha)
        self.assertEqual(state["deployed_sha"], self.sha)

    def test_missing_or_invalid_marker_cannot_verify_release(self) -> None:
        self.assertFalse(release_state()["release_verified"])
        self.marker.write_text("not-a-sha", encoding="utf-8")
        self.assertIsNone(release_state()["deployed_sha"])
        self.assertFalse(release_state()["release_verified"])

    def test_mismatched_marker_is_not_verified(self) -> None:
        self.marker.write_text("b" * 40, encoding="utf-8")
        state = release_state()
        self.assertEqual(state["active_release_sha"], self.sha)
        self.assertFalse(state["release_verified"])

    def test_unexpected_symlink_destination_is_not_verified(self) -> None:
        self.marker.write_text(self.sha, encoding="utf-8")
        elsewhere = self.root / self.sha
        elsewhere.mkdir()
        (self.runtime / "current").unlink()
        (self.runtime / "current").symlink_to(elsewhere, target_is_directory=True)
        state = release_state()
        self.assertIsNone(state["active_release_sha"])
        self.assertFalse(state["release_verified"])

    def test_non_symlink_current_does_not_verify(self) -> None:
        self.marker.write_text(self.sha, encoding="utf-8")
        (self.runtime / "current").unlink()
        (self.runtime / "current").mkdir()
        self.assertFalse(release_state()["release_verified"])


if __name__ == "__main__":
    unittest.main()
