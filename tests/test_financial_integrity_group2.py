from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.db import get_conn, init_db, now_iso
from core.payroll_engine import compute_13th_month_basis, update_payroll_status


class FinancialIntegrityRegressionTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        handle.close()
        self.path = Path(handle.name)
        self.conn = get_conn(self.path)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)
        Path(str(self.path) + "-wal").unlink(missing_ok=True)
        Path(str(self.path) + "-shm").unlink(missing_ok=True)

    def add_run(self, status, regular, leave=0, superseded_by=None):
        cursor = self.conn.execute(
            """INSERT INTO payroll_runs(period_start,period_end,payout_date,run_label,status,created_at,superseded_by_run_id)
               VALUES('2026-09-15','2026-09-29','2026-09-30',?,?,?,?)""",
            (f"Regression {status}", status, now_iso(), superseded_by),
        )
        run_id = int(cursor.lastrowid)
        self.conn.execute(
            """INSERT INTO payroll_items(payroll_run_id,employee_id,regular_pay,paid_leave_pay,created_at)
               VALUES(?,?,?,?,?)""",
            (run_id, 1, regular, leave, now_iso()),
        )
        self.conn.commit()
        return run_id

    def test_13th_month_excludes_superseded_and_unapproved_versions(self):
        old = self.add_run("Approved", 1000, 100)
        current = self.add_run("Paid", 1200, 150)
        self.conn.execute("UPDATE payroll_runs SET superseded_by_run_id=? WHERE id=?", (current, old))
        self.add_run("For Owner Review", 5000, 500)
        self.add_run("Draft", 8000, 800)
        self.conn.commit()
        self.assertEqual(compute_13th_month_basis(self.conn, 1, 2026), 1350)

    def test_repeated_paid_transition_does_not_reapply_side_effects(self):
        run_id = self.add_run("Paid", 1200)
        with patch("core.payroll_engine.apply_cash_advance_repayments") as repayments:
            update_payroll_status(self.conn, run_id, "Paid", "Owner")
            repayments.assert_not_called()

    def test_paid_and_locked_cannot_be_reopened(self):
        for status in ("Paid", "Locked"):
            run_id = self.add_run(status, 100)
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "Finalized payroll"):
                    update_payroll_status(self.conn, run_id, "Draft", "Owner", reason="Change")


if __name__ == "__main__":
    unittest.main()
