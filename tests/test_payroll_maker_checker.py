from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from core.payroll_maker_checker import assert_distinct_checker


class PayrollMakerCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE payroll_adjustment_events (payroll_run_id INTEGER NOT NULL, actor_name TEXT)"
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_preparer_owner_can_approve_same_run(self) -> None:
        run = {"id": 41, "prepared_by": "Owner One"}
        assert_distinct_checker(self.conn, run, " owner   one ")

    def test_material_adjuster_owner_can_approve_same_run(self) -> None:
        self.conn.execute(
            "INSERT INTO payroll_adjustment_events(payroll_run_id,actor_name) VALUES(?,?)",
            (42, "Owner One"),
        )
        run = {"id": 42, "prepared_by": "Owner One"}
        assert_distinct_checker(self.conn, run, "OWNER ONE")

    def test_approval_still_requires_attributed_owner(self) -> None:
        run = {"id": 43, "prepared_by": "Payroll Clerk"}
        with self.assertRaisesRegex(ValueError, "attributed owner account"):
            assert_distinct_checker(self.conn, run, "   ")

    def test_canonical_approval_endpoint_remains_owner_only(self) -> None:
        source = Path("api/payroll_service.py").read_text(encoding="utf-8")
        role_guard = source.index('if user.get("role_key") != "owner":')
        transition = source.index('update_payroll_status(conn, run_id, "Approved", actor)')
        self.assertLess(role_guard, transition)

    def test_same_owner_can_approve_run_they_prepared(self) -> None:
        import api.payroll_service as service

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE payroll_runs (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                prepared_by TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT,
                approved_by TEXT,
                approved_at TEXT,
                paid_by TEXT,
                paid_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE TABLE payroll_adjustment_events (payroll_run_id INTEGER NOT NULL, actor_name TEXT)"
        )
        conn.execute(
            "CREATE TABLE payroll_items (payroll_run_id INTEGER, gross_pay REAL DEFAULT 0, net_pay REAL DEFAULT 0, total_deductions REAL DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO payroll_runs(id,status,prepared_by) VALUES(1,?,?)",
            ("For Owner Review", "Owner One"),
        )
        conn.commit()

        with (
            patch.object(service, "must_be_payroll_user", return_value={"role_key": "owner", "display_name": "Owner One"}),
            patch.object(service, "get_conn", return_value=conn),
        ):
            response = service.approve_payroll_run(1, "token", "key")

        self.assertTrue(response["ok"])
        self.assertEqual("Approved", response["run"]["status"])
        self.assertEqual("Owner One", response["run"]["approved_by"])


if __name__ == "__main__":
    unittest.main()
