from __future__ import annotations

import inspect
import unittest

from api import payroll_mark_paid


class MarkPaidUtcTimestampTests(unittest.TestCase):
    def test_mark_paid_uses_shared_utc_storage_clock(self) -> None:
        source = inspect.getsource(payroll_mark_paid.mark_payroll_run_paid)
        self.assertIn("paid_at = now_iso()", source)
        self.assertNotIn("datetime('now','localtime')", source)

    def test_unpaid_replacement_revision_can_continue_to_payment(self) -> None:
        source = inspect.getsource(payroll_mark_paid.mark_payroll_run_paid)
        self.assertIn('treatment == "replace_unpaid" and original_paid', source)
        self.assertNotIn('original.get("status") not in {"Paid", "Locked", "Released"}', source)
        self.assertIn('treatment == "adjust_paid" and not original_paid', source)

    def test_only_paid_adjustment_revision_reverses_prior_repayments(self) -> None:
        source = inspect.getsource(payroll_mark_paid.mark_payroll_run_paid)
        guard = source.index('if treatment == "adjust_paid":')
        reversal = source.index("reverse_payroll_cash_advance_repayments(", guard)
        update = source.index('UPDATE payroll_runs SET superseded_by_run_id=?', reversal)
        self.assertLess(guard, reversal)
        self.assertLess(reversal, update)


if __name__ == "__main__":
    unittest.main()
