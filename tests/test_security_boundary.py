from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import api.main as legacy
import api.security as security


class SecurityBoundaryTests(unittest.TestCase):
    def test_role_contract_matches_existing_behavior(self) -> None:
        samples = {
            "Owner": "owner",
            "Administrator": "owner",
            "Payroll Admin": "payroll",
            "General Manager": "supervisor",
            "Department Head": "supervisor",
            "Employee": "staff",
            None: "staff",
        }
        for value, expected in samples.items():
            self.assertEqual(security.role_to_key(value), expected)
            self.assertEqual(security.role_to_key(value), legacy.role_to_key(value))

    def test_session_tokens_round_trip_through_boundary(self) -> None:
        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_SESSION_SECRET": "test-security-boundary-secret"},
            clear=False,
        ):
            payload = {"sub": 7, "role": "owner", "sv": 1, "exp": 4102444800}
            token = security.sign_payload(payload)
            self.assertEqual(security.verify_token(token), payload)
            self.assertEqual(token, legacy.sign_payload(payload))

    def test_boundary_exports_canonical_dependencies(self) -> None:
        self.assertIs(security.require_api_key, legacy.require_api_key)
        self.assertIs(security.require_roles, legacy.require_roles)
        self.assertIs(security.current_user_from_token, legacy.current_user_from_token)


if __name__ == "__main__":
    unittest.main()
