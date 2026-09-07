from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api import cash_advance_service as service


def _user(role_key: str) -> dict[str, str]:
    return {"role_key": role_key, "display_name": role_key.title()}


class CashAdvanceCreationAuthorizationTests(unittest.TestCase):
    def test_supervisor_remains_viewer_but_cannot_create_cash_advance(self) -> None:
        with patch.object(service, "current_user_from_token", return_value=_user("supervisor")):
            viewer = service.require_cash_advance_viewer("Bearer supervisor", None)
            self.assertEqual(viewer["role_key"], "supervisor")

            with self.assertRaises(HTTPException) as exc_info:
                service.require_cash_advance_creator("Bearer supervisor", None)

        self.assertEqual(exc_info.exception.status_code, 403)

    def test_owner_can_create_cash_advances(self) -> None:
        with patch.object(service, "current_user_from_token", return_value=_user("owner")):
            user = service.require_cash_advance_creator("Bearer owner", None)
        self.assertEqual(user["role_key"], "owner")

    def test_payroll_can_create_cash_advances(self) -> None:
        with patch.object(service, "current_user_from_token", return_value=_user("payroll")):
            user = service.require_cash_advance_creator("Bearer payroll", None)
        self.assertEqual(user["role_key"], "payroll")

    def test_api_key_system_creation_remains_payroll_scoped(self) -> None:
        with patch.object(service, "require_api_key", return_value=None):
            user = service.require_cash_advance_creator(None, "integration-key")
        self.assertEqual(user["role_key"], "payroll")


if __name__ == "__main__":
    unittest.main()
