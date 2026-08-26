from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.mfa_security import (
    consume_recovery_code,
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
                "STAFF_PAYROLL_MFA_KEY": "unit-test-mfa-encryption-key-that-is-long-enough",
                "STAFF_PAYROLL_ENV": "test",
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
        self.assertEqual(decrypt_mfa_secret(stored), secret)

    def test_plaintext_secret_remains_legacy_compatible_outside_production(self) -> None:
        self.assertEqual(
            decrypt_mfa_secret("JBSWY3DPEHPK3PXP"),
            "JBSWY3DPEHPK3PXP",
        )

    def test_plaintext_secret_is_refused_in_production(self) -> None:
        with patch.dict(os.environ, {"STAFF_PAYROLL_ENV": "production"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "plaintext MFA secret refused"):
                decrypt_mfa_secret("JBSWY3DPEHPK3PXP")

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

    def test_recovery_code_is_consumed_once(self) -> None:
        codes = generate_recovery_codes()
        stored = hash_recovery_codes(codes)
        ok, remaining = consume_recovery_code(stored, codes[0])
        self.assertTrue(ok)
        self.assertEqual(len(remaining), len(stored) - 1)
        reused, after_reuse = consume_recovery_code(remaining, codes[0])
        self.assertFalse(reused)
        self.assertEqual(after_reuse, remaining)

    def test_invalid_recovery_code_does_not_modify_set(self) -> None:
        codes = generate_recovery_codes()
        stored = hash_recovery_codes(codes)
        ok, remaining = consume_recovery_code(stored, "INVALID-CODE")
        self.assertFalse(ok)
        self.assertEqual(remaining, stored)


if __name__ == "__main__":
    unittest.main()
