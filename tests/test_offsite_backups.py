from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from core.offsite_backups import copy_offsite, sha256_file, verify_offsite_copy


S3_ENV = {
    "STAFF_PAYROLL_OFFSITE_BACKUP_DIR": "",
    "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "https://hel1.your-objectstorage.com",
    "STAFF_PAYROLL_OFFSITE_S3_REGION": "hel1",
    "STAFF_PAYROLL_OFFSITE_S3_BUCKET": "hidden-oasis-backups",
    "STAFF_PAYROLL_OFFSITE_S3_PREFIX": "staff/payroll",
    "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID": "test-access-key",
    "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY": "test-secret-key",
}


class OffsiteBackupTests(unittest.TestCase):
    def test_partial_s3_configuration_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STAFF_PAYROLL_OFFSITE_BACKUP_DIR": "",
                "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT": "https://hel1.your-objectstorage.com",
                "STAFF_PAYROLL_OFFSITE_S3_BUCKET": "",
                "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID": "",
                "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY": "",
            },
            clear=False,
        ):
            with tempfile.TemporaryDirectory() as temp_dir:
                source = Path(temp_dir) / "staff-payroll-package-test.zip.fernet"
                source.write_bytes(b"encrypted-backup")
                with self.assertRaises(RuntimeError):
                    copy_offsite(source)

    def test_s3_upload_records_sha256_metadata(self) -> None:
        client = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "staff-payroll-package-test.zip.fernet"
            source.write_bytes(b"encrypted-backup")
            with patch.dict(os.environ, S3_ENV, clear=False), patch(
                "core.offsite_backups._s3_client", return_value=client
            ):
                destination = copy_offsite(source)

        self.assertEqual(
            destination,
            "s3://hidden-oasis-backups/staff/payroll/staff-payroll-package-test.zip.fernet",
        )
        client.upload_file.assert_called_once()
        call = client.upload_file.call_args
        self.assertEqual(call.args[1], "hidden-oasis-backups")
        self.assertEqual(
            call.args[2],
            "staff/payroll/staff-payroll-package-test.zip.fernet",
        )
        metadata = call.kwargs["ExtraArgs"]["Metadata"]
        self.assertEqual(metadata["sha256"], sha256_file(source))
        self.assertEqual(metadata["bytes"], str(source.stat().st_size))
        self.assertEqual(metadata["encrypted"], "true")

    def test_s3_head_verification_requires_size_and_sha_match(self) -> None:
        client = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "staff-payroll-package-test.zip.fernet"
            source.write_bytes(b"encrypted-backup")
            client.head_object.return_value = {
                "ContentLength": source.stat().st_size,
                "Metadata": {"sha256": sha256_file(source)},
                "LastModified": datetime.now(timezone.utc),
            }
            with patch.dict(os.environ, S3_ENV, clear=False), patch(
                "core.offsite_backups._s3_client", return_value=client
            ):
                result = verify_offsite_copy(source)

        self.assertTrue(result["configured"])
        self.assertTrue(result["exists"])
        self.assertTrue(result["matching"])
        self.assertEqual(result["kind"], "s3")

    def test_preflight_documents_and_checks_s3_offsite_support(self) -> None:
        preflight = Path("scripts/production_preflight.py").read_text(encoding="utf-8")
        example = Path(".env.example").read_text(encoding="utf-8")
        requirements = Path("requirements-api.txt").read_text(encoding="utf-8")
        self.assertIn("verify_offsite_copy", preflight)
        for token in (
            "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT=",
            "STAFF_PAYROLL_OFFSITE_S3_BUCKET=",
            "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID=",
            "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY=",
        ):
            self.assertIn(token, example)
        self.assertIn("boto3==", requirements)


if __name__ == "__main__":
    unittest.main()
