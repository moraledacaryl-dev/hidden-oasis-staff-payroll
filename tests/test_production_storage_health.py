from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.production_health import backup_age_limit_hours, filesystem_capacity
from core.offsite_backups import offsite_configuration_status


class ProductionStorageHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def check(self, *, free_blocks: int, free_inodes: int = 40) -> list[dict]:
        stat = SimpleNamespace(
            f_blocks=100,
            f_bavail=free_blocks,
            f_frsize=10,
            f_favail=free_inodes,
            f_files=100,
        )
        with (
            patch.dict(os.environ, {
                "STAFF_PAYROLL_MIN_FREE_DISK_BYTES": "100",
                "STAFF_PAYROLL_MIN_FREE_DISK_PERCENT": "10",
                "STAFF_PAYROLL_MIN_FREE_INODE_PERCENT": "10",
            }),
            patch("api.production_health.os.statvfs", return_value=stat),
        ):
            return filesystem_capacity([self.root, self.root / "uncreated" / "database"])

    def test_healthy_device_passes_and_is_reported_once(self) -> None:
        rows = self.check(free_blocks=25)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["free_percent"], 25)
        self.assertEqual(rows[0]["free_inode_percent"], 40)
        self.assertTrue(rows[0]["deployment_space_ok"])

    def test_low_disk_space_fails_closed_without_writing(self) -> None:
        before = list(self.root.iterdir())
        rows = self.check(free_blocks=5)
        self.assertFalse(rows[0]["deployment_space_ok"])
        self.assertEqual(rows[0]["free_percent"], 5)
        self.assertEqual(list(self.root.iterdir()), before)

    def test_low_inode_capacity_is_a_separate_gate(self) -> None:
        rows = self.check(free_blocks=25, free_inodes=5)
        self.assertFalse(rows[0]["deployment_space_ok"])

    def test_uninspectable_filesystem_is_reported_not_ignored(self) -> None:
        with patch("api.production_health.os.statvfs", side_effect=OSError("unavailable")):
            rows = filesystem_capacity([self.root])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["deployment_space_ok"])
        self.assertEqual(rows[0]["error"], "Filesystem unavailable")

    def test_invalid_threshold_config_uses_conservative_default(self) -> None:
        stat = SimpleNamespace(f_blocks=100, f_bavail=25, f_frsize=10, f_favail=40, f_files=100)
        with (
            patch.dict(os.environ, {"STAFF_PAYROLL_MIN_FREE_DISK_BYTES": "not-a-number"}),
            patch("api.production_health.os.statvfs", return_value=stat),
        ):
            rows = filesystem_capacity([self.root])
        self.assertEqual(rows[0]["minimum_free_gib"], 2.0)
        self.assertFalse(rows[0]["deployment_space_ok"])


    def test_offsite_configuration_status_uses_s3_and_never_exposes_secrets(self) -> None:
        variables = {
            "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "https://backups.example.com",
            "STAFF_PAYROLL_OFFSITE_S3_BUCKET": "private-bucket",
            "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID": "private-access-id",
            "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY": "private-secret",
        }
        with patch.dict(os.environ, variables, clear=True):
            status = offsite_configuration_status()
        self.assertEqual(status, "s3_configured_not_verified")
        self.assertNotIn("private", status)

    def test_offsite_status_incomplete_s3_does_not_claim_configuration(self) -> None:
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "https://backups.example.com",
            "STAFF_PAYROLL_OFFSITE_S3_BUCKET": "private-bucket",
        }, clear=True):
            self.assertEqual(offsite_configuration_status(), "s3_configuration_incomplete")
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "http://insecure.example.com",
            "STAFF_PAYROLL_OFFSITE_S3_BUCKET": "private-bucket",
            "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID": "key",
            "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY": "secret",
        }, clear=True):
            self.assertEqual(offsite_configuration_status(), "s3_configuration_incomplete")

    def test_offsite_status_directory_precedence_and_absence(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(offsite_configuration_status(), "not_configured")
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_OFFSITE_BACKUP_DIR": "/mnt/remote",
            "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "http://unused",
        }, clear=True):
            self.assertEqual(offsite_configuration_status(), "directory_configured")

    def test_backup_age_limit_matches_deploy_preflight_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(backup_age_limit_hours(), 26)
        with patch.dict(os.environ, {"STAFF_PAYROLL_MAX_BACKUP_AGE_HOURS": "48"}):
            self.assertEqual(backup_age_limit_hours(), 48)
        with patch.dict(os.environ, {"STAFF_PAYROLL_MAX_BACKUP_AGE_HOURS": "invalid"}):
            self.assertEqual(backup_age_limit_hours(), 26)
        with patch.dict(os.environ, {"STAFF_PAYROLL_MAX_BACKUP_AGE_HOURS": "0"}):
            self.assertEqual(backup_age_limit_hours(), 1)


if __name__ == "__main__":
    unittest.main()
