from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.runtime_guard import validate_runtime_environment


GOOD = {
    "STAFF_PAYROLL_ENV": "production",
    "STAFF_PAYROLL_API_KEY": "ApiKey-7jK9mQ2xV5pR8sT1uW4yZ6aB3cD0eF",
    "STAFF_PAYROLL_SESSION_SECRET": "Session-4nP8qR2tV6xZ1bD5fH9jL3mN7sW0yC",
    "STAFF_PAYROLL_MFA_KEY": "MfaKey-6cF1hJ5mQ9tW3xZ7bD2nP8rV4yK0sL",
    "STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "true",
}


class RuntimeGuardSecurityTests(unittest.TestCase):
    def test_strong_distinct_production_configuration_passes(self) -> None:
        with patch.dict(os.environ, GOOD, clear=True):
            validate_runtime_environment()

    def test_weak_secret_is_rejected(self) -> None:
        env = {**GOOD, "STAFF_PAYROLL_API_KEY": "x"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "at least 32 bytes"):
                validate_runtime_environment()

    def test_placeholder_secret_is_rejected(self) -> None:
        env = {**GOOD, "STAFF_PAYROLL_SESSION_SECRET": "replace-with-this-placeholder-value-123456789"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "placeholder/default"):
                validate_runtime_environment()

    def test_equal_secrets_are_rejected(self) -> None:
        env = {**GOOD, "STAFF_PAYROLL_MFA_KEY": GOOD["STAFF_PAYROLL_API_KEY"]}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "independent values"):
                validate_runtime_environment()

    def test_privileged_mfa_must_be_enabled_in_production(self) -> None:
        env = {**GOOD, "STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "false"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "must be true in production"):
                validate_runtime_environment()

    def test_whitespace_secret_is_rejected(self) -> None:
        env = {**GOOD, "STAFF_PAYROLL_MFA_KEY": "Mfa Key-6cF1hJ5mQ9tW3xZ7bD2nP8rV4yK0sL"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "contains whitespace"):
                validate_runtime_environment()

    def test_nonproduction_keeps_development_flexible(self) -> None:
        with patch.dict(os.environ, {"STAFF_PAYROLL_ENV": "test"}, clear=True):
            validate_runtime_environment()


if __name__ == "__main__":
    unittest.main()
