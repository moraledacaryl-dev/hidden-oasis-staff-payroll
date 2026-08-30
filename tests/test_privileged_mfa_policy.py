from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from api.security import (
    privileged_mfa_required,
    public_user,
)


class PrivilegedMfaPolicyTests(unittest.TestCase):
    def test_owner_without_mfa_is_not_blocked_by_default(self) -> None:
        user = {
            "role": "Owner",
            "mfa_enabled": 0,
        }

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA", None)
            self.assertFalse(privileged_mfa_required(user))
            self.assertEqual(public_user(user)["mfa_setup_required"], 0)

    def test_owner_without_mfa_is_not_blocked_when_policy_disabled(self) -> None:
        user = {
            "role": "Owner",
            "mfa_enabled": 0,
        }

        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "false"},
        ):
            self.assertFalse(privileged_mfa_required(user))
            self.assertEqual(public_user(user)["mfa_setup_required"], 0)

    def test_owner_without_mfa_requires_setup_when_policy_enabled(self) -> None:
        user = {
            "role": "Owner",
            "mfa_enabled": 0,
        }

        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "true"},
        ):
            self.assertTrue(privileged_mfa_required(user))
            self.assertEqual(public_user(user)["mfa_setup_required"], 1)

    def test_payroll_without_mfa_requires_setup_when_policy_enabled(self) -> None:
        user = {
            "role": "Payroll",
            "mfa_enabled": 0,
        }

        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "true"},
        ):
            self.assertTrue(privileged_mfa_required(user))

    def test_general_manager_does_not_require_mfa(self) -> None:
        user = {
            "role": "General Manager",
            "mfa_enabled": 0,
        }

        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "true"},
        ):
            self.assertFalse(privileged_mfa_required(user))

    def test_staff_does_not_require_mfa(self) -> None:
        user = {
            "role": "Staff",
            "mfa_enabled": 0,
        }

        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "true"},
        ):
            self.assertFalse(privileged_mfa_required(user))

    def test_enabled_owner_satisfies_enabled_policy(self) -> None:
        user = {
            "role": "Owner",
            "mfa_enabled": 1,
        }

        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA": "true"},
        ):
            self.assertFalse(privileged_mfa_required(user))


if __name__ == "__main__":
    unittest.main()
