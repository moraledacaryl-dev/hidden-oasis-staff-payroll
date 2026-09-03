from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from fastapi import HTTPException

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

    def test_preparer_cannot_approve_same_run(self) -> None:
        run = {"id": 41, "prepared_by": "Owner One"}
        with self.assertRaisesRegex(ValueError, "Maker-checker separation"):
            assert_distinct_checker(self.conn, run, " owner   one ")

    def test_material_adjuster_cannot_approve_even_when_someone_else_prepared(self) -> None:
        self.conn.execute(
            "INSERT INTO payroll_adjustment_events(payroll_run_id,actor_name) VALUES(?,?)",
            (42, "Owner One"),
        )
        run = {"id": 42, "prepared_by": "Payroll Clerk"}
        with self.assertRaisesRegex(ValueError, "materially adjusted"):
            assert_distinct_checker(self.conn, run, "OWNER ONE")

    def test_different_owner_can_approve_payroll_prepared_and_adjusted_by_others(self) -> None:
        self.conn.execute(
            "INSERT INTO payroll_adjustment_events(payroll_run_id,actor_name) VALUES(?,?)",
            (43, "Payroll Clerk"),
        )
        run = {"id": 43, "prepared_by": "Payroll Clerk"}
        assert_distinct_checker(self.conn, run, "Owner One")

    def test_canonical_approval_endpoint_enforces_control_before_status_update(self) -> None:
        source = Path("api/payroll_service.py").read_text(encoding="utf-8")
        guard = source.index("assert_distinct_checker(conn, run, actor)")
        transition = source.index('update_payroll_status(conn, run_id, "Approved", actor)')
        self.assertLess(guard, transition)

    def test_same_actor_rejection_is_exposed_as_conflict(self) -> None:
        from unittest.mock import patch
        import api.payroll_service as service

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE payroll_runs (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                prepared_by TEXT
            )
            """
        )
        conn.execute(
            "CREATE TABLE payroll_adjustment_events (payroll_run_id INTEGER NOT NULL, actor_name TEXT)"
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
            with self.assertRaises(HTTPException) as raised:
                service.approve_payroll_run(1, "token", "key")

        self.assertEqual(409, raised.exception.status_code)
        self.assertIn("Maker-checker separation", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
