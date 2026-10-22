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
        self.module_path = self.active / "api" / "production_health.py"
        self.module_path.parent.mkdir()
        self.module_path.write_text("", encoding="utf-8")
        module_patch = patch("api.production_health.__file__", str(self.module_path))
        module_patch.start()
        self.addCleanup(module_patch.stop)
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
        self.assertEqual(state["running_api_sha"], self.sha)

    def test_missing_or_invalid_marker_cannot_verify_release(self) -> None:
        self.assertFalse(release_state()["release_verified"])
        self.marker.write_text("not-a-sha", encoding="utf-8")
        self.assertIsNone(release_state()["deployed_sha"])
        self.assertFalse(release_state()["release_verified"])

    def test_running_api_from_previous_release_is_not_verified(self) -> None:
        self.marker.write_text(self.sha, encoding="utf-8")
        old_release = self.releases / ("c" * 40)
        old_api = old_release / "api" / "production_health.py"
        old_api.parent.mkdir(parents=True)
        old_api.write_text("", encoding="utf-8")
        with patch("api.production_health.__file__", str(old_api)):
            state = release_state()
        self.assertEqual(state["active_release_sha"], self.sha)
        self.assertEqual(state["running_api_sha"], "c" * 40)
        self.assertFalse(state["release_verified"])

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
