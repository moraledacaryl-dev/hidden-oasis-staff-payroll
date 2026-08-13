from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.mfa_security import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_recovery_codes,
    hash_recovery_code,
    hash_recovery_codes,
)


class MfaSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(
            os.environ,
            {
                "STAFF_PAYROLL_MFA_KEY":
                    "unit-test-mfa-encryption-key-that-is-long-enough",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_mfa_secret_round_trip_is_encrypted(self) -> None:
        secret = "JBSWY3DPEHPK3PXP"

        stored = encrypt_mfa_secret(secret)

        self.assertNotEqual(stored, secret)
        self.assertTrue(stored.startswith("fernet:"))
        self.assertEqual(
            decrypt_mfa_secret(stored),
            secret,
        )

    def test_plaintext_secret_remains_legacy_compatible(self) -> None:
        self.assertEqual(
            decrypt_mfa_secret("JBSWY3DPEHPK3PXP"),
            "JBSWY3DPEHPK3PXP",
        )

    def test_recovery_codes_are_unique(self) -> None:
        codes = generate_recovery_codes()

        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)

    def test_recovery_code_hash_is_deterministic(self) -> None:
        self.assertEqual(
            hash_recovery_code("abcd1234-ef567890"),
            hash_recovery_code("ABCD1234-EF567890"),
        )

    def test_only_hashes_need_to_be_persisted(self) -> None:
        codes = generate_recovery_codes()
        hashes = hash_recovery_codes(codes)

        for code in codes:
            self.assertNotIn(code, hashes)


if __name__ == "__main__":
    unittest.main()
