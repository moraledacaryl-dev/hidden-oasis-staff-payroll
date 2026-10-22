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

    def test_supervisor_ui_does_not_offer_write_only_repayment_action(self) -> None:
        from pathlib import Path

        source = Path("apps/web/app/cash-advances/page.tsx").read_text(encoding="utf-8")
        self.assertIn('canEditExisting && item.status !== "Cancelled"', source)
        self.assertIn("<ManualRepaymentForm advanceId={item.id}", source)
        self.assertIn('Number(item.release_confirmation_required || 0) !== 1 || item.released_at', source)

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
