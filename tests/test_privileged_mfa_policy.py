from __future__ import annotations

import unittest

from api.security import (
    privileged_mfa_required,
    public_user,
)


class PrivilegedMfaPolicyTests(unittest.TestCase):
    def test_owner_without_mfa_requires_setup(self) -> None:
        user = {
            "role": "Owner",
            "mfa_enabled": 0,
        }

        self.assertTrue(
            privileged_mfa_required(user)
        )

        self.assertEqual(
            public_user(user)["mfa_setup_required"],
            1,
        )

    def test_payroll_without_mfa_requires_setup(self) -> None:
        user = {
            "role": "Payroll",
            "mfa_enabled": 0,
        }

        self.assertTrue(
            privileged_mfa_required(user)
        )

    def test_general_manager_does_not_require_mfa(self) -> None:
        user = {
            "role": "General Manager",
            "mfa_enabled": 0,
        }

        self.assertFalse(
            privileged_mfa_required(user)
        )

    def test_staff_does_not_require_mfa(self) -> None:
        user = {
            "role": "Staff",
            "mfa_enabled": 0,
        }

        self.assertFalse(
            privileged_mfa_required(user)
        )

    def test_enabled_owner_satisfies_policy(self) -> None:
        user = {
            "role": "Owner",
            "mfa_enabled": 1,
        }

        self.assertFalse(
            privileged_mfa_required(user)
        )


if __name__ == "__main__":
    unittest.main()
