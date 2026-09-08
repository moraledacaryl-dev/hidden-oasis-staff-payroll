from __future__ import annotations

import inspect
import unittest

from api import payroll_mark_paid


class MarkPaidUtcTimestampTests(unittest.TestCase):
    def test_mark_paid_uses_shared_utc_storage_clock(self) -> None:
        source = inspect.getsource(payroll_mark_paid.mark_payroll_run_paid)
        self.assertIn("paid_at = now_iso()", source)
        self.assertNotIn("datetime('now','localtime')", source)


if __name__ == "__main__":
    unittest.main()
