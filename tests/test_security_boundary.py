from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

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

    def test_session_tokens_round_trip_and_match_legacy_contract(self) -> None:
        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_SESSION_SECRET": "test-security-boundary-secret"},
            clear=False,
        ):
            payload = {"sub": 7, "role": "owner", "sv": 1, "exp": 4102444800}
            token = security.sign_payload(payload)
            self.assertEqual(security.verify_token(token), payload)
            self.assertEqual(token, legacy.sign_payload(payload))
            self.assertEqual(legacy.verify_token(token), payload)

    def test_api_key_behavior_matches_legacy_contract(self) -> None:
        with patch.dict(
            os.environ,
            {"STAFF_PAYROLL_API_KEY": "expected-key"},
            clear=False,
        ):
            security.require_api_key("expected-key")
            with self.assertRaises(HTTPException) as context:
                security.require_api_key("wrong-key")
            self.assertEqual(context.exception.status_code, 401)

    def test_security_module_does_not_import_legacy_api_main(self) -> None:
        path = Path(security.__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        direct_imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("api.main", imported_modules)
        self.assertNotIn("api.main", direct_imports)

    def test_public_user_contract_matches_legacy_behavior(self) -> None:
        record = {
            "id": 4,
            "display_name": "General Manager",
            "role": "Supervisor",
            "active": 1,
            "must_change_password": 1,
            "employee_id": 12,
            "session_version": 3,
            "last_login_at": "2026-08-06 10:00:00",
        }
        self.assertEqual(security.public_user(record), legacy.public_user(record))


if __name__ == "__main__":
    unittest.main()
