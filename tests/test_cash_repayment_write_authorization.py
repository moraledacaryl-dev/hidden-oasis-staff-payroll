from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import api.cash_advance_service as cash_service
import api.cash_repayments as cash_repayments


class CashRepaymentWriteAuthorizationTests(unittest.TestCase):
    def test_manual_repayment_endpoint_uses_editor_authorization(self) -> None:
        source = inspect.getsource(cash_repayments.record_manual_repayment)
        self.assertIn("require_cash_advance_editor(authorization, x_api_key)", source)
        self.assertNotIn("require_cash_advance_viewer(authorization, x_api_key)", source)

    def test_supervisor_is_rejected_for_financial_write(self) -> None:
        with patch.object(
            cash_service,
            "current_user_from_token",
            return_value={"id": 44, "display_name": "Supervisor", "role_key": "supervisor"},
        ):
            with self.assertRaises(HTTPException) as ctx:
                cash_service.require_cash_advance_editor("Bearer supervisor", None)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_and_payroll_remain_authorized_financial_editors(self) -> None:
        for role in ("owner", "payroll"):
            with self.subTest(role=role):
                expected = {"id": 1, "display_name": role.title(), "role_key": role}
                with patch.object(cash_service, "current_user_from_token", return_value=expected):
                    self.assertEqual(
                        cash_service.require_cash_advance_editor(f"Bearer {role}", None),
                        expected,
                    )


if __name__ == "__main__":
    unittest.main()
