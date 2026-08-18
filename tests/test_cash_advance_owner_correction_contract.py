from __future__ import annotations

import unittest
from pathlib import Path


class CashAdvanceOwnerCorrectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.component = Path("apps/web/components/CashAdvanceBalanceCorrection.tsx").read_text(encoding="utf-8")
        cls.page = Path("apps/web/app/cash-advances/page.tsx").read_text(encoding="utf-8")
        cls.editor = Path("apps/web/components/CashAdvanceFormV2.tsx").read_text(encoding="utf-8")
        cls.backend = Path("api/cash_advance_corrections.py").read_text(encoding="utf-8")

    def test_owner_only_action_is_rendered_from_page(self) -> None:
        self.assertIn("{isOwner ? <CashAdvanceBalanceCorrection", self.page)
        self.assertIn("ledger_opening_balance?: number | null", self.page)
        self.assertIn("currentBasis={basis}", self.page)
        self.assertIn("totalRepaid={repaid}", self.page)

    def test_general_editor_keeps_balance_basis_read_only(self) -> None:
        self.assertIn('disabled={Boolean(item)}', self.editor)
        self.assertIn("Read-only here. Owners must use the separate Correct balance basis action.", self.editor)
        self.assertNotIn('action: "correct_amount"', self.editor)
        self.assertNotIn("correction_reason", self.editor)

    def test_correction_submits_only_the_dedicated_action(self) -> None:
        self.assertIn('action: "correct_amount"', self.component)
        self.assertIn("cash_advance_id: advanceId", self.component)
        self.assertIn("corrected_amount: basis", self.component)
        self.assertIn("correction_reason: reason.trim()", self.component)
        self.assertNotIn('id: advanceId', self.component)
        self.assertNotIn("repayment_method", self.component)

    def test_correction_requires_reason_and_explicit_confirmation(self) -> None:
        self.assertIn('if (!reason.trim())', self.component)
        self.assertIn('if (!confirmed)', self.component)
        self.assertIn("I reviewed the new remaining balance and any employee credit.", self.component)
        self.assertIn("Confirm correction", self.component)

    def test_projection_covers_lower_basis_and_overpayment_credit(self) -> None:
        self.assertIn("const projectedBalance = Math.max(0, basis - repaid);", self.component)
        self.assertIn("const projectedCredit = Math.max(0, repaid - basis);", self.component)
        self.assertIn("Previous basis", self.component)
        self.assertIn("Repayments applied", self.component)
        self.assertIn("Projected remaining", self.component)
        self.assertIn("Employee credit", self.component)

    def test_backend_remains_owner_only_and_audited(self) -> None:
        self.assertIn('if user.get("role_key") != "owner":', self.backend)
        self.assertIn('@router.post("/cash-advances/{cash_advance_id}/correct-amount")', self.backend)
        self.assertIn("cash_advance_amount_corrections", self.backend)
        self.assertIn("correction_reason", self.backend)
        self.assertIn("overpayment_credit", self.backend)


if __name__ == "__main__":
    unittest.main()
