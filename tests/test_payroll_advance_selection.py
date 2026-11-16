from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api import payroll_adjustments_aggregate as aggregate
from api import payroll_mark_paid
from api.cash_advance_service import calculate_balance
from api.payroll_adjustments import (
    AdjustmentPayload, AdvanceAllocationPayload,
    ensure_schema as ensure_adjustment_schema,
)
from api.payroll_mark_paid import MarkPaidRequest
from api.payroll_revision_workflow import carry_forward_manual_values
from core.cash_advance_payroll import apply_payroll_cash_advance_repayments
from core.db import fetchone, get_conn, init_db, now_iso
from tests.test_multi_cash_advance_payroll import _seed_advance, _seed_employee, _seed_run


class PayrollAdvanceSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "payroll.sqlite"
        conn = get_conn(self.path)
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            self.employee = _seed_employee(conn)
            self.run = _seed_run(conn, self.employee, deduction=0)
            self.first = _seed_advance(
                conn, self.employee, advance_date="2026-08-01",
                amount=300, deduction_per_payroll=100,
            )
            self.second = _seed_advance(
                conn, self.employee, advance_date="2026-08-10",
                amount=500, deduction_per_payroll=100,
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def save(self, run_id: int, allocations: list[tuple[int, float]], *,
             version: int = 0, note: str = "Owner selected these advances") -> dict:
        payload = AdjustmentPayload(
            cash_advance_allocation_mode="manual",
            cash_advance_allocations=[
                AdvanceAllocationPayload(cash_advance_id=i, amount=amount)
                for i, amount in allocations
            ],
            cash_advance_amount=sum(amount for _, amount in allocations),
            cash_advance_note=note,
            expected_version=version,
        )
        with (
            patch.object(aggregate, "DB_PATH", self.path),
            patch.object(
                aggregate, "must_be_payroll_user",
                return_value={"role_key": "owner", "display_name": "Owner"},
            ),
        ):
            return aggregate.save_adjustments(run_id, self.employee, payload, "token")

    def mark_paid(self, run_id: int) -> dict:
        with (
            patch.object(payroll_mark_paid, "DB_PATH", self.path),
            patch.object(
                payroll_mark_paid, "must_be_payroll_user",
                return_value={"role_key": "owner", "display_name": "Owner"},
            ),
            patch.object(payroll_mark_paid, "build_payroll_preflight_checks", return_value=[]),
            patch.object(payroll_mark_paid, "create_accounting_queue_for_payroll"),
            patch("core.integration_accounting.enqueue_payroll_run"),
        ):
            return payroll_mark_paid.mark_payroll_run_paid(
                run_id, MarkPaidRequest(confirmation="MARK PAID"), "token", "key",
            )

    def test_select_second_advance_without_touching_first_and_post_only_when_paid(self):
        self.save(self.run, [(self.second, 150)])
        conn = get_conn(self.path)
        try:
            plan = fetchone(
                conn, "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=?", (self.run,),
            )
            self.assertEqual(plan["cash_advance_allocation_mode"], "manual")
            self.assertIn('"cash_advance_id":' + str(self.second), plan["cash_advance_allocations_json"])
            self.assertEqual(calculate_balance(conn, self.first)["balance"], 300)
            self.assertEqual(calculate_balance(conn, self.second)["balance"], 500)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM cash_advance_repayments WHERE payroll_run_id=?", (self.run,)
            ).fetchone()[0], 0)
            conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=?", (self.run,))
            conn.commit()
        finally:
            conn.close()

        self.mark_paid(self.run)
        conn = get_conn(self.path)
        try:
            rows = conn.execute(
                "SELECT cash_advance_id,amount FROM cash_advance_repayments "
                "WHERE payroll_run_id=? AND COALESCE(active,1)=1",
                (self.run,),
            ).fetchall()
            self.assertEqual([tuple(row) for row in rows], [(self.second, 150)])
            self.assertEqual(calculate_balance(conn, self.first)["balance"], 300)
            self.assertEqual(calculate_balance(conn, self.second)["balance"], 350)
            apply_payroll_cash_advance_repayments(conn, self.run, actor="Owner")
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM cash_advance_repayments WHERE payroll_run_id=?", (self.run,)
            ).fetchone()[0], 1)
        finally:
            conn.close()

    def test_split_two_advances_and_edit_same_total_before_payment(self):
        saved = self.save(self.run, [(self.first, 80), (self.second, 120)])
        self.assertEqual(saved["version"], 1)
        edited = self.save(
            self.run, [(self.first, 30), (self.second, 170)], version=1,
        )
        self.assertEqual(edited["version"], 2)
        conn = get_conn(self.path)
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM payroll_adjustment_events WHERE payroll_run_id=? "
                "AND adjustment_kind='cash_advance_allocation'", (self.run,)
            ).fetchone()[0], 2)
            self.assertEqual(calculate_balance(conn, self.first)["balance"], 300)
            self.assertEqual(calculate_balance(conn, self.second)["balance"], 500)
            conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=?", (self.run,))
            conn.commit()
        finally:
            conn.close()
        self.mark_paid(self.run)
        conn = get_conn(self.path)
        try:
            rows = conn.execute(
                "SELECT cash_advance_id,amount FROM cash_advance_repayments WHERE payroll_run_id=? "
                "AND COALESCE(active,1)=1 ORDER BY cash_advance_id",
                (self.run,),
            ).fetchall()
            self.assertEqual([tuple(row) for row in rows], [(self.first, 30), (self.second, 170)])
        finally:
            conn.close()

    def test_reject_over_balance_duplicate_and_changed_balance_before_paid(self):
        with self.assertRaises(HTTPException) as exceeded:
            self.save(self.run, [(self.first, 301)])
        self.assertEqual(exceeded.exception.status_code, 422)
        with self.assertRaises(HTTPException) as duplicates:
            self.save(self.run, [(self.first, 10), (self.first, 20)])
        self.assertEqual(duplicates.exception.status_code, 422)
        self.save(self.run, [(self.first, 200)])
        conn = get_conn(self.path)
        try:
            conn.execute(
                "INSERT INTO cash_advance_repayments("
                "cash_advance_id,employee_id,repayment_date,payment_date,"
                "amount,source,active,created_at) VALUES(?,?,?,?,?,'Manual',1,?)",
                (self.first, self.employee, "2026-08-20", "2026-08-20", 150, now_iso()),
            )
            conn.execute("UPDATE payroll_runs SET status='Approved' WHERE id=?", (self.run,))
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(HTTPException) as failed:
            self.mark_paid(self.run)
        self.assertEqual(failed.exception.status_code, 409)
        conn = get_conn(self.path)
        try:
            self.assertEqual(
                conn.execute("SELECT status FROM payroll_runs WHERE id=?", (self.run,)).fetchone()[0],
                "Approved",
            )
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM cash_advance_repayments WHERE payroll_run_id=?", (self.run,)
            ).fetchone()[0], 0)
        finally:
            conn.close()

    def test_prior_manual_draft_reserves_target_not_older_advance(self):
        self.save(self.run, [(self.second, 150)])
        conn = get_conn(self.path)
        try:
            later_run = _seed_run(conn, self.employee, deduction=0, period_end="2026-09-15")
            conn.commit()
            later = aggregate._cash_snapshot(
                conn, run_id=later_run, employee_id=self.employee,
                period_end="2026-09-15", amount=100,
            )
            available = {row["id"]: row["available_balance"] for row in later["cash_advances"]}
            self.assertEqual(available[self.first], 300)
            self.assertEqual(available[self.second], 350)
            self.assertEqual(later["cash_advance_reserved_elsewhere"], 150)
        finally:
            conn.close()

    def test_unpaid_replacement_carries_exact_allocation_plan(self):
        self.save(self.run, [(self.second, 125)])
        conn = get_conn(self.path)
        try:
            replacement = _seed_run(conn, self.employee, deduction=0, period_end="2026-09-15")
            copied = carry_forward_manual_values(
                conn, self.run, replacement, "replace_unpaid", now_iso(), "Owner",
            )
            conn.commit()
            self.assertEqual(copied, 1)
            record = fetchone(
                conn, "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=?",
                (replacement,),
            )
            self.assertEqual(record["cash_advance_allocation_mode"], "manual")
            self.assertIn('"cash_advance_id":' + str(self.second), record["cash_advance_allocations_json"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
