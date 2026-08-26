from __future__ import annotations

import unittest
from pathlib import Path


class ProductionRecoveryGateContractTests(unittest.TestCase):
    def test_preflight_requires_backup_offsite_restore_and_capacity_gates(self) -> None:
        source = Path("scripts/production_preflight.py").read_text(encoding="utf-8")
        for token in (
            "STAFF_PAYROLL_BACKUP_KEY",
            "verify_offsite_copy",
            "STAFF_PAYROLL_MAX_BACKUP_AGE_HOURS",
            "STAFF_PAYROLL_RESTORE_DRILL_MARKER",
            "STAFF_PAYROLL_MAX_RESTORE_DRILL_AGE_DAYS",
            "STAFF_PAYROLL_MIN_FREE_DISK_BYTES",
            "STAFF_PAYROLL_MIN_FREE_DISK_PERCENT",
            "STAFF_PAYROLL_MIN_FREE_INODE_PERCENT",
            "verify_backup",
        ):
            self.assertIn(token, source)

    def test_preflight_checks_schema_and_outbox_thresholds(self) -> None:
        source = Path("scripts/production_preflight.py").read_text(encoding="utf-8")
        self.assertIn("from core.db import MIGRATIONS", source)
        self.assertIn("schema migrations current through", source)
        self.assertIn("STAFF_PAYROLL_MAX_ACTIVE_OUTBOX_AGE_MINUTES", source)
        self.assertIn("STAFF_PAYROLL_MAX_DEAD_LETTERS", source)
        self.assertIn('"Pending", "Retry", "Processing", "Ready", "Error"', source)

    def test_restore_drill_materializes_and_validates_backup(self) -> None:
        source = Path("scripts/restore_drill.py").read_text(encoding="utf-8")
        self.assertIn("_read_backup_payload", source)
        self.assertIn('archive.read("database/staff-payroll.sqlite")', source)
        self.assertIn('PRAGMA integrity_check', source)
        self.assertIn('PRAGMA quick_check', source)
        self.assertIn("REQUIRED_TABLES", source)
        self.assertIn("STAFF_PAYROLL_RESTORE_DRILL_MARKER", source)
        self.assertIn('marker.chmod(0o600)', source)

    def test_example_documents_recovery_configuration(self) -> None:
        source = Path(".env.example").read_text(encoding="utf-8")
        for token in (
            "STAFF_PAYROLL_BACKUP_DIR=",
            "STAFF_PAYROLL_BACKUP_KEY=",
            "STAFF_PAYROLL_OFFSITE_BACKUP_DIR=",
            "STAFF_PAYROLL_RESTORE_DRILL_MARKER=",
            "STAFF_PAYROLL_MAX_BACKUP_AGE_HOURS=",
            "STAFF_PAYROLL_MAX_RESTORE_DRILL_AGE_DAYS=",
            "STAFF_PAYROLL_MAX_ACTIVE_OUTBOX_AGE_MINUTES=",
            "STAFF_PAYROLL_MAX_DEAD_LETTERS=",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
