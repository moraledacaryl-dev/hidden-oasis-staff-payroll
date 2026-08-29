from __future__ import annotations

import unittest
from pathlib import Path


class P2ConfirmationModalContractTests(unittest.TestCase):
    def test_confirmation_modal_uses_app_modal_and_supports_typed_guard(self) -> None:
        source = Path("apps/web/components/ConfirmActionModal.tsx").read_text(encoding="utf-8")

        self.assertIn('import { AppModal } from "@/components/AppSurface";', source)
        self.assertIn("confirmationText?: string", source)
        self.assertIn("typed.trim() === confirmationText", source)
        self.assertIn("disabled={!canConfirm}", source)
        self.assertIn("autoFocus={!requiresTypedConfirmation}", source)

    def test_app_surfaces_have_named_dialogs_and_focus_containment(self) -> None:
        source = Path("apps/web/components/AppSurface.tsx").read_text(encoding="utf-8")

        self.assertGreaterEqual(source.count("aria-labelledby={titleId}"), 2)
        self.assertGreaterEqual(source.count("aria-describedby={description ? descriptionId : undefined}"), 2)
        self.assertGreaterEqual(source.count('role="dialog"'), 2)
        self.assertIn("FOCUSABLE_SELECTOR", source)
        self.assertIn('event.key !== "Tab"', source)
        self.assertIn("previousFocus?.focus()", source)
        self.assertIn("onCloseRef.current()", source)

    def test_schedule_publication_uses_in_app_confirmation(self) -> None:
        source = Path("apps/web/components/SchedulePublicationPanel.tsx").read_text(encoding="utf-8")

        self.assertNotIn("window.confirm", source)
        self.assertIn("<ConfirmActionModal", source)
        self.assertIn('title={republish ? "Republish revised schedule" : "Publish schedule"}', source)

    def test_payroll_recalculate_uses_in_app_confirmation(self) -> None:
        source = Path("apps/web/components/RecalculatePayrollButton.tsx").read_text(encoding="utf-8")

        self.assertNotIn("window.confirm", source)
        self.assertIn("<ConfirmActionModal", source)
        self.assertIn('title="Recalculate payroll draft"', source)

    def test_mark_paid_requires_typed_in_app_confirmation(self) -> None:
        source = Path("apps/web/components/PayrollLifecycleButtons.tsx").read_text(encoding="utf-8")

        self.assertNotIn("window.confirm", source)
        self.assertIn("<ConfirmActionModal", source)
        self.assertIn('confirmationText="MARK PAID"', source)
        self.assertIn('description="This finalizes payment and applies cash-advance repayments', source)
        self.assertIn('onConfirm={() => submit("paid")}', source)

    def test_schedule_clear_day_uses_in_app_confirmation(self) -> None:
        source = Path("apps/web/components/ScheduleBoardClient.tsx").read_text(encoding="utf-8")

        self.assertNotIn("window.confirm", source)
        self.assertIn("type ClearPrompt", source)
        self.assertIn("<ConfirmActionModal", source)
        self.assertIn('title="Clear this schedule day?"', source)
        self.assertIn('body: JSON.stringify({ section: "reset", employee_id: employeeId, work_date: workDate })', source)

    def test_standalone_mark_paid_uses_shared_app_modal_and_keeps_typed_guard(self) -> None:
        source = Path("apps/web/components/MarkPaidButton.tsx").read_text(encoding="utf-8")

        self.assertIn('import { AppModal } from "@/components/AppSurface";', source)
        self.assertIn("<AppModal", source)
        self.assertIn('confirmation !== "MARK PAID"', source)
        self.assertIn("body: JSON.stringify({ run_id: runId, confirmation, reference })", source)


if __name__ == "__main__":
    unittest.main()
