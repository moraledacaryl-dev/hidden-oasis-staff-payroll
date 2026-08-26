from __future__ import annotations

import unittest
from pathlib import Path


class PayrollAdjustmentAuditContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend = Path("api/payroll_adjustments.py").read_text(encoding="utf-8")
        cls.events = Path("api/payroll_adjustment_events.py").read_text(encoding="utf-8")
        cls.audit = Path("api/payroll_audit_events.py").read_text(encoding="utf-8")
        cls.editor = Path("apps/web/components/PayrollAdjustmentEditor.tsx").read_text(encoding="utf-8")
        cls.proxy = Path("apps/web/app/api/payroll/runs/[id]/employees/[employeeId]/adjustments/route.ts").read_text(encoding="utf-8")

    def test_append_only_event_schema_uses_centavos_and_attribution(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS payroll_adjustment_events", self.events)
        for field in ("old_centavos", "new_centavos", "actor_id", "actor_name", "request_id", "created_at"):
            self.assertIn(field, self.events)
        self.assertNotIn("UPDATE payroll_adjustment_events", self.events)
        self.assertNotIn("DELETE FROM payroll_adjustment_events", self.events)

    def test_events_are_written_before_single_commit(self) -> None:
        append_at = self.backend.index("append_adjustment_event(")
        commit_at = self.backend.index("conn.commit()", append_at)
        self.assertLess(append_at, commit_at)
        self.assertIn("old_centavos=to_centavos(old_value)", self.backend)
        self.assertIn("new_centavos=to_centavos(new_value)", self.backend)

    def test_nonzero_manual_adjustments_require_reasons(self) -> None:
        self.assertIn('if earning > 0 and not earning_note:', self.backend)
        self.assertIn('if other > 0 and not other_note:', self.backend)
        self.assertIn("A reason is required for additional earnings.", self.backend)
        self.assertIn("A reason is required for other deductions.", self.backend)

    def test_cash_advance_deviation_requires_reason(self) -> None:
        self.assertIn("cash != suggested_cash and not cash_note", self.backend)
        self.assertIn("cash_advance_note", self.backend)
        self.assertIn("cashNeedsReason", self.editor)
        self.assertIn('name="cash_advance_note"', self.editor)

    def test_optimistic_concurrency_rejects_stale_writes(self) -> None:
        self.assertIn("expected_version: int = 0", self.backend)
        self.assertIn("current_version", self.backend)
        self.assertIn("status_code=409", self.backend)
        self.assertIn("WHERE payroll_run_id=? AND employee_id=? AND version=?", self.backend)
        self.assertIn("expected_version: Number(adjustment.version ?? 0)", self.editor)
        self.assertIn("if (response.status === 409) void load();", self.editor)

    def test_proxy_adds_request_id_and_revalidates_audit(self) -> None:
        self.assertIn('headers["X-Request-ID"]', self.proxy)
        self.assertIn("randomUUID()", self.proxy)
        self.assertIn('revalidatePath(`/payroll/runs/${id}/audit`)', self.proxy)

    def test_run_audit_stream_includes_adjustment_events(self) -> None:
        self.assertIn('table_exists(conn, "payroll_adjustment_events")', self.audit)
        self.assertIn('"payroll_adjustment_events"', self.audit)
        self.assertIn("old_centavos", self.audit)
        self.assertIn("new_centavos", self.audit)
        self.assertIn("request_id", self.audit)

    def test_current_state_projection_keeps_version_and_cash_note(self) -> None:
        self.assertIn("cash_advance_note TEXT", self.backend)
        self.assertIn("version INTEGER NOT NULL DEFAULT 1", self.backend)
        self.assertIn('ALTER TABLE payroll_item_adjustments ADD COLUMN cash_advance_note TEXT', self.backend)
        self.assertIn('ALTER TABLE payroll_item_adjustments ADD COLUMN version INTEGER NOT NULL DEFAULT 1', self.backend)


if __name__ == "__main__":
    unittest.main()
