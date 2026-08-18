from __future__ import annotations

import unittest
from pathlib import Path


class CashAdvanceLifecycleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend = Path("api/cash_advances.py").read_text(encoding="utf-8")
        cls.form = Path("apps/web/components/CashAdvanceFormV2.tsx").read_text(encoding="utf-8")
        cls.proxy = Path("apps/web/app/api/cash-advances/route.ts").read_text(encoding="utf-8")

    def test_ordinary_edit_does_not_write_status(self) -> None:
        marker = "Lifecycle status is deliberately immutable through ordinary detail edits."
        self.assertIn(marker, self.backend)
        update = self.backend.split(marker, 1)[1].split("_sync_legacy_fields", 1)[0]
        self.assertNotIn("status=?", update)
        self.assertNotIn("payload.status", update)

    def test_status_is_not_a_general_edit_control(self) -> None:
        self.assertNotIn('name="status"', self.form)
        self.assertNotIn('status: String(formData.get("status")', self.form)
        self.assertNotIn("<option>Fully Paid</option>", self.form)

    def test_lifecycle_actions_are_explicit(self) -> None:
        self.assertIn('/cash-advances/{cash_advance_id}/approve', self.backend)
        self.assertIn('/cash-advances/{cash_advance_id}/reject', self.backend)
        self.assertIn('/cash-advances/{cash_advance_id}/cancel', self.backend)
        self.assertIn('allowed_from={"Pending", "Rejected"}', self.backend)
        self.assertIn('allowed_from={"Pending"}', self.backend)
        self.assertIn('allowed_from={"Pending", "Rejected", "Active"}', self.backend)
        self.assertIn('status_code=409', self.backend)

    def test_reject_and_cancel_require_reason(self) -> None:
        self.assertGreaterEqual(self.backend.count("reason_required=True"), 2)
        self.assertIn("Reason for reject/cancel", self.form)

    def test_proxy_routes_only_named_transition_actions(self) -> None:
        self.assertIn('new Set(["approve", "reject", "cancel"])', self.proxy)
        self.assertIn('`${apiBaseUrl()}/api/v1/cash-advances/${cashAdvanceId}/${action}`', self.proxy)

    def test_lifecycle_changes_are_append_only_audited(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS cash_advance_lifecycle_events", self.backend)
        self.assertIn("INSERT INTO cash_advance_lifecycle_events", self.backend)


if __name__ == "__main__":
    unittest.main()
