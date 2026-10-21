"""Ensure browser review fixture is executable before expensive visual smoke tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class BrowserSmokeHandoffFixtureTests(unittest.TestCase):
    def test_synthetic_fully_paid_manual_repayment_has_no_outbox(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "staff-smoke.sqlite"
            environment = dict(os.environ)
            environment.update({
                "STAFF_PAYROLL_ENV": "test",
                "STAFF_PAYROLL_DB_PATH": str(database),
                "STAFF_PAYROLL_SESSION_SECRET": "only-for-disposable-browser-test",
            })
            completed = subprocess.run(
                [sys.executable, "scripts/browser_smoke_seed.py"],
                env=environment,
                text=True,
                capture_output=True,
                check=True,
                timeout=45,
            )
            payload = json.loads(completed.stdout)
            self.assertTrue(all(payload["tokens"].get(role) for role in
                                ("owner", "supervisor", "staff")))
            self.assertTrue(database.is_file())
            with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
                conn.execute("PRAGMA query_only=ON")
                cases = conn.execute("""
                    SELECT r.id, r.amount, ca.status, ca.remaining_balance
                    FROM cash_advance_repayments r
                    JOIN cash_advances ca ON ca.id=r.cash_advance_id
                    WHERE LOWER(TRIM(r.source))='manual'
                      AND COALESCE(r.active,1)=1
                      AND NOT EXISTS (
                        SELECT 1 FROM integration_outbox o
                        WHERE o.destination='accounting'
                          AND o.external_source='hidden_oasis_staff_payroll'
                          AND o.event_type='cash_advance.repaid'
                          AND o.external_id='cash-advance-repayment:' || r.id
                      )
                """).fetchall()
            self.assertEqual(len(cases), 1)
            self.assertEqual(float(cases[0][1]), 1200)
            self.assertEqual(cases[0][2], "Fully Paid")
            self.assertEqual(float(cases[0][3]), 0)


if __name__ == "__main__":
    unittest.main()
