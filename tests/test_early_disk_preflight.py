from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.check_predeploy_disk_space import GIB, capacity_status, main


class EarlyDiskPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, free_bytes: int, *, free_inodes: int = 50) -> list[dict[str, object]]:
        disk = SimpleNamespace(total=100 * GIB, used=100 * GIB - free_bytes, free=free_bytes)
        inodes = SimpleNamespace(f_files=100, f_favail=free_inodes)
        with (
            patch("scripts.check_predeploy_disk_space.shutil.disk_usage", return_value=disk),
            patch("scripts.check_predeploy_disk_space.os.statvfs", return_value=inodes),
        ):
            return capacity_status(
                [self.root / "db", self.root / "backups"],
                min_bytes=2 * GIB,
                min_percent=10,
                min_inode_percent=10,
            )

    def test_one_percent_disk_free_fails_before_deployment_writes(self) -> None:
        result = self._run(1 * GIB)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["free_percent"], 1)
        self.assertFalse(result[0]["ok"])

    def test_space_and_inode_thresholds_require_both_conditions(self) -> None:
        enough = self._run(12 * GIB)
        self.assertTrue(enough[0]["ok"])
        low_inode = self._run(12 * GIB, free_inodes=1)
        self.assertFalse(low_inode[0]["ok"])
        self.assertEqual(low_inode[0]["free_inodes_percent"], 1)

    def test_not_enough_absolute_bytes_fails_even_if_percentage_is_large(self) -> None:
        disk = SimpleNamespace(total=5 * GIB, used=4 * GIB, free=1 * GIB)
        inodes = SimpleNamespace(f_files=100, f_favail=100)
        with (
            patch("scripts.check_predeploy_disk_space.shutil.disk_usage", return_value=disk),
            patch("scripts.check_predeploy_disk_space.os.statvfs", return_value=inodes),
        ):
            result = capacity_status(
                [self.root],
                min_bytes=2 * GIB,
                min_percent=10,
                min_inode_percent=10,
            )
        self.assertFalse(result[0]["ok"])

    def test_deploy_checks_space_before_pip_and_new_backup(self) -> None:
        script = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        guard = 'python3 "$APP_ROOT/scripts/check_predeploy_disk_space.py"'
        self.assertIn(guard, script)
        self.assertLess(script.index(guard), script.index("Installing source API dependencies"))
        self.assertLess(script.index(guard), script.index("Creating pre-deploy database backup"))
        self.assertIn('"$SOURCE_PYTHON" scripts/production_preflight.py', script)

    def test_missing_paths_fail_closed(self) -> None:
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_DB_PATH": "",
            "STAFF_PAYROLL_BACKUP_DIR": "",
        }):
            self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
