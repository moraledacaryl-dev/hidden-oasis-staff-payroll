from __future__ import annotations

import unittest

from api.cash_advance_service import ensure_schema as ensure_cash_schema
from api.payroll_adjustments import ensure_schema as ensure_adjustment_schema
from api.payroll_adjustments_aggregate import _cash_snapshot
from core.cash_advance_payroll import apply_payroll_cash_advance_repayments
from core.db import get_conn, init_db, now_iso


def _seed_employee(conn) -> int:
    stamp = now_iso()
    cursor = conn.execute(
        """
        INSERT INTO employees(
            employee_code,full_name,status,created_at,updated_at
        ) VALUES('EMP-MULTI','Multiple Advance Employee','Active',?,?)
        """,
        (stamp, stamp),
    )
    return int(cursor.lastrowid)


def _seed_run(conn, employee_id: int, *, deduction: float, period_end: str = "2026-08-31") -> int:
    from datetime import date, timedelta
    stamp = now_iso()
    payout = (date.fromisoformat(period_end) + timedelta(days=1)).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO payroll_runs(
            period_start,period_end,payout_date,run_label,status,created_at
        ) VALUES('2026-08-16',?,?,'Test','Draft',?)
        """,
        (period_end, payout, stamp),
    )
    run_id = int(cursor.lastrowid)
    conn.execute(
        """
        INSERT INTO payroll_items(
            payroll_run_id,employee_id,gross_pay,cash_advance_deduction,
            total_deductions,net_pay,created_at
        ) VALUES(?,?,1000,?,?,?,?)
        """,
        (run_id, employee_id, deduction, deduction, 1000 - deduction, stamp),
    )
    return run_id


def _seed_advance(
    conn,
    employee_id: int,
    *,
    advance_date: str,
    amount: float,
    deduction_per_payroll: float,
) -> int:
    stamp = now_iso()
    cursor = conn.execute(
        """
        INSERT INTO cash_advances(
            employee_id,request_date,advance_date,amount,
            outstanding_balance,remaining_balance,
            repayment_method,deduction_per_payroll,status,created_at
        ) VALUES(?,?,?,?,?,?,'Payroll deduction',?,'Active',?)
        """,
        (
            employee_id,
            advance_date,
            advance_date,
            amount,
            amount,
            amount,
            deduction_per_payroll,
            stamp,
        ),
    )
    return int(cursor.lastrowid)


class MultiCashAdvancePayrollTests(unittest.TestCase):
    def test_aggregate_snapshot_spans_multiple_advances_and_respects_other_drafts(self) -> None:
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=0)
            other_run_id = _seed_run(conn, employee_id, deduction=50, period_end="2026-09-15")
            first = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-01",
                amount=100,
                deduction_per_payroll=100,
            )
            second = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=200,
                deduction_per_payroll=100,
            )
            other_item = conn.execute(
                "SELECT id FROM payroll_items WHERE payroll_run_id=? AND employee_id=?",
                (other_run_id, employee_id),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO payroll_item_adjustments(
                    payroll_run_id,payroll_item_id,employee_id,
                    cash_advance_amount,version,created_at,updated_at
                ) VALUES(?,?,?,50,1,?,?)
                """,
                (other_run_id, int(other_item[0]), employee_id, now_iso(), now_iso()),
            )
            conn.commit()

            snapshot = _cash_snapshot(
                conn,
                run_id=run_id,
                employee_id=employee_id,
                period_end="2026-08-31",
                amount=180,
            )

            # The future September draft cannot reserve the August advance.
            self.assertEqual(snapshot["cash_advance_reserved_elsewhere"], 0)
            self.assertEqual(snapshot["cash_advance_total_available"], 300)
            self.assertEqual(snapshot["cash_advance_suggested"], 200)
            self.assertEqual(
                snapshot["cash_advance_allocations"],
                [
                    {
                        "cash_advance_id": first,
                        "advance_date": "2026-08-01",
                        "reason": None,
                        "available_balance": 100.0,
                        "amount": 100.0,
                    },
                    {
                        "cash_advance_id": second,
                        "advance_date": "2026-08-10",
                        "reason": None,
                        "available_balance": 200.0,
                        "amount": 80.0,
                    },
                ],
            )
        finally:
            conn.close()

    def test_earlier_draft_reservation_applies_to_later_payday(self) -> None:
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            early_run = _seed_run(conn, employee_id, deduction=1000)
            later_run = _seed_run(conn, employee_id, deduction=0, period_end="2026-09-15")
            advance_id = _seed_advance(
                conn, employee_id, advance_date="2026-08-10",
                amount=3000, deduction_per_payroll=3000,
            )
            item_id = conn.execute(
                "SELECT id FROM payroll_items WHERE payroll_run_id=?",
                (early_run,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO payroll_item_adjustments("
                "payroll_run_id,payroll_item_id,employee_id,cash_advance_amount,"
                "version,created_at,updated_at) VALUES(?,?,?,1000,1,?,?)",
                (early_run, item_id, employee_id, now_iso(), now_iso()),
            )
            conn.commit()

            earlier = _cash_snapshot(
                conn, run_id=early_run, employee_id=employee_id,
                period_end="2026-08-31", amount=1000,
            )
            later = _cash_snapshot(
                conn, run_id=later_run, employee_id=employee_id,
                period_end="2026-09-15", amount=1000,
            )
            self.assertEqual(earlier["cash_advance_total_available"], 3000)
            self.assertEqual(earlier["cash_advance_reserved_elsewhere"], 0)
            self.assertEqual(later["cash_advance_total_available"], 2000)
            self.assertEqual(later["cash_advance_reserved_elsewhere"], 1000)
            self.assertEqual(later["cash_advances"][0]["id"], advance_id)
        finally:
            conn.close()

    def test_payday_advance_is_visible_and_posts_once(self) -> None:
        from api.cash_advance_service import calculate_balance
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=1000)
            advance_id = _seed_advance(
                conn, employee_id, advance_date="2026-09-01",
                amount=3000, deduction_per_payroll=1000,
            )
            conn.execute(
                "UPDATE cash_advances SET release_confirmation_required=1,"
                "released_at='2026-09-01' WHERE id=?",
                (advance_id,),
            )
            conn.commit()
            snapshot = _cash_snapshot(
                conn, run_id=run_id, employee_id=employee_id,
                period_end="2026-08-31", amount=1000,
            )
            self.assertEqual(snapshot["cash_advance_deduction_date"], "2026-09-01")
            self.assertEqual(snapshot["cash_advance_total_available"], 3000)
            apply_payroll_cash_advance_repayments(conn, run_id, actor="Owner")
            apply_payroll_cash_advance_repayments(conn, run_id, actor="Owner")
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM cash_advance_repayments "
                    "WHERE payroll_run_id=? AND active=1",
                    (run_id,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(calculate_balance(conn, advance_id)["balance"], 3000)
            # Draft repayment rows cannot reduce the live balance until paid.
            conn.execute("UPDATE payroll_runs SET status='Paid' WHERE id=?", (run_id,))
            self.assertEqual(calculate_balance(conn, advance_id)["balance"], 2000)
        finally:
            conn.close()

    def test_zero_availability_explains_unconfirmed_issuance(self) -> None:
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=0)
            advance_id = _seed_advance(
                conn, employee_id, advance_date="2026-08-10",
                amount=3000, deduction_per_payroll=1000,
            )
            conn.execute(
                "UPDATE cash_advances SET release_confirmation_required=1,"
                "released_at=NULL WHERE id=?",
                (advance_id,),
            )
            conn.commit()
            snapshot = _cash_snapshot(
                conn, run_id=run_id, employee_id=employee_id,
                period_end="2026-08-31", amount=0,
            )
            self.assertEqual(snapshot["cash_advance_total_available"], 0)
            self.assertTrue(any(
                "not been confirmed issued" in note
                for note in snapshot["cash_advance_availability_notes"]
            ))
        finally:
            conn.close()

    def test_zero_ledger_basis_flags_review_without_fabricating_debt(self) -> None:
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=0)
            advance_id = _seed_advance(
                conn, employee_id, advance_date="2026-08-10",
                amount=3000, deduction_per_payroll=1000,
            )
            conn.execute(
                "UPDATE cash_advances SET ledger_opening_balance=0,"
                "status='Fully Paid' WHERE id=?",
                (advance_id,),
            )
            conn.commit()
            snapshot = _cash_snapshot(
                conn, run_id=run_id, employee_id=employee_id,
                period_end="2026-08-31", amount=0,
            )
            self.assertEqual(snapshot["cash_advance_total_available"], 0)
            self.assertTrue(any(
                "recorded opening balance is zero" in note
                for note in snapshot["cash_advance_availability_notes"]
            ))
            self.assertEqual(
                conn.execute(
                    "SELECT ledger_opening_balance FROM cash_advances WHERE id=?",
                    (advance_id,),
                ).fetchone()[0],
                0,
            )
        finally:
            conn.close()

    def test_migration_prefers_real_remaining_over_default_zero(self) -> None:
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_cash_schema(conn)
            employee_id = _seed_employee(conn)
            advance_id = _seed_advance(
                conn, employee_id, advance_date="2026-08-10",
                amount=3000, deduction_per_payroll=1000,
            )
            conn.execute(
                "UPDATE cash_advances SET outstanding_balance=0,"
                "remaining_balance=3000,ledger_opening_balance=NULL WHERE id=?",
                (advance_id,),
            )
            ensure_cash_schema(conn)
            self.assertEqual(
                conn.execute(
                    "SELECT ledger_opening_balance FROM cash_advances WHERE id=?",
                    (advance_id,),
                ).fetchone()[0],
                3000,
            )
            conn.execute(
                "UPDATE cash_advances SET ledger_opening_balance=0,"
                "remaining_balance=0,outstanding_balance=0 WHERE id=?",
                (advance_id,),
            )
            ensure_cash_schema(conn)
            self.assertEqual(
                conn.execute(
                    "SELECT ledger_opening_balance FROM cash_advances WHERE id=?",
                    (advance_id,),
                ).fetchone()[0],
                0,
            )
        finally:
            conn.close()

    def test_paid_payroll_deduction_posts_across_multiple_advances_fifo(self) -> None:
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_cash_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=250)
            first = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-01",
                amount=100,
                deduction_per_payroll=100,
            )
            second = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=200,
                deduction_per_payroll=100,
            )
            future = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-09-02",
                amount=500,
                deduction_per_payroll=500,
            )
            conn.commit()

            apply_payroll_cash_advance_repayments(conn, run_id, actor="Owner")
            conn.commit()

            rows = conn.execute(
                """
                SELECT cash_advance_id, amount
                FROM cash_advance_repayments
                WHERE payroll_run_id=? AND COALESCE(active,1)=1
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
            self.assertEqual(
                [(int(row[0]), float(row[1])) for row in rows],
                [(first, 100.0), (second, 150.0)],
            )
            self.assertTrue(all(int(row[0]) != future for row in rows))
        finally:
            conn.close()


    def test_stale_fully_paid_status_cannot_hide_an_unrepaid_draft_advance(self) -> None:
        """A cached status from an old draft must not stand in for a payment."""
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=0)
            advance_id = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=3000,
                deduction_per_payroll=3000,
            )
            conn.execute(
                "UPDATE cash_advances SET status='Fully Paid' WHERE id=?",
                (advance_id,),
            )
            conn.commit()

            snapshot = _cash_snapshot(
                conn,
                run_id=run_id,
                employee_id=employee_id,
                period_end="2026-08-31",
                amount=1000,
                persist_balances=True,
            )
            self.assertEqual(snapshot["cash_advance_total_available"], 3000)
            self.assertEqual(snapshot["cash_advance_allocations"][0]["amount"], 1000)
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM cash_advances WHERE id=?", (advance_id,)
                ).fetchone()[0],
                "Active",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM cash_advance_repayments WHERE cash_advance_id=?",
                    (advance_id,),
                ).fetchone()[0],
                0,
            )
        finally:
            conn.close()

    def test_superseded_draft_deduction_does_not_reserve_the_balance(self) -> None:
        """An old superseded draft must not consume a current draft's capacity."""
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            old_run_id = _seed_run(conn, employee_id, deduction=3000)
            current_run_id = _seed_run(conn, employee_id, deduction=0, period_end="2026-09-15")
            _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=3000,
                deduction_per_payroll=3000,
            )
            # Old app databases lack this later revision schema addition.
            conn.execute("ALTER TABLE payroll_runs ADD COLUMN superseded_by_run_id INTEGER")
            conn.execute(
                "UPDATE payroll_runs SET superseded_by_run_id=? WHERE id=?",
                (current_run_id, old_run_id),
            )
            old_item_id = int(
                conn.execute(
                    "SELECT id FROM payroll_items WHERE payroll_run_id=?",
                    (old_run_id,),
                ).fetchone()[0]
            )
            conn.execute(
                """
                INSERT INTO payroll_item_adjustments(
                    payroll_run_id,payroll_item_id,employee_id,
                    cash_advance_amount,version,created_at,updated_at
                ) VALUES(?,?,?,3000,1,?,?)
                """,
                (old_run_id, old_item_id, employee_id, now_iso(), now_iso()),
            )
            conn.commit()

            snapshot = _cash_snapshot(
                conn,
                run_id=current_run_id,
                employee_id=employee_id,
                period_end="2026-09-15",
                amount=1000,
            )
            self.assertEqual(snapshot["cash_advance_reserved_elsewhere"], 0)
            self.assertEqual(snapshot["cash_advance_total_available"], 3000)
            self.assertEqual(snapshot["cash_advance_allocations"][0]["amount"], 1000)
        finally:
            conn.close()

    def test_a_genuinely_fully_repaid_advance_is_still_unavailable(self) -> None:
        """Do not re-enable deductions against a legitimately zero balance."""
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=0)
            advance_id = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=3000,
                deduction_per_payroll=3000,
            )
            conn.execute(
                """
                INSERT INTO cash_advance_repayments(
                    cash_advance_id,employee_id,repayment_date,payment_date,amount,source,active,created_at
                ) VALUES(?,?,?,?,3000,'Manual',1,?)
                """,
                (advance_id, employee_id, "2026-08-20", "2026-08-20", now_iso()),
            )
            conn.execute(
                "UPDATE cash_advances SET status='Fully Paid' WHERE id=?",
                (advance_id,),
            )
            conn.commit()

            snapshot = _cash_snapshot(
                conn,
                run_id=run_id,
                employee_id=employee_id,
                period_end="2026-08-31",
                amount=1000,
            )
            self.assertEqual(snapshot["cash_advance_total_available"], 0)
            self.assertEqual(snapshot["cash_advances"], [])
        finally:
            conn.close()



    def test_stale_fully_paid_label_posts_only_when_run_is_paid(self) -> None:
        """A deduction accepted for a draft is not silently skipped on payout."""
        from api.cash_advance_service import recalculate_balance

        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=1000)
            advance_id = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=3000,
                deduction_per_payroll=3000,
            )
            conn.execute(
                "UPDATE cash_advances SET status='Fully Paid' WHERE id=?",
                (advance_id,),
            )
            conn.execute(
                "UPDATE payroll_runs SET status='Paid' WHERE id=?",
                (run_id,),
            )
            conn.commit()

            apply_payroll_cash_advance_repayments(conn, run_id, actor="Owner")
            conn.commit()
            self.assertEqual(
                conn.execute(
                    "SELECT amount FROM cash_advance_repayments "
                    "WHERE cash_advance_id=? AND payroll_run_id=? AND active=1",
                    (advance_id, run_id),
                ).fetchone()[0],
                1000,
            )
            self.assertEqual(recalculate_balance(conn, advance_id)["balance"], 2000)
            apply_payroll_cash_advance_repayments(conn, run_id, actor="Owner")
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM cash_advance_repayments "
                    "WHERE cash_advance_id=? AND payroll_run_id=? AND active=1",
                    (advance_id, run_id),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(recalculate_balance(conn, advance_id)["balance"], 2000)
        finally:
            conn.close()

    def test_unreleased_advance_is_not_offered_for_payroll_deduction(self) -> None:
        """An approved advance is not necessarily cash actually issued."""
        from types import SimpleNamespace
        from api.payroll_drafts import _apply_period_cash_advance_deduction

        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_adjustment_schema(conn)
            employee_id = _seed_employee(conn)
            run_id = _seed_run(conn, employee_id, deduction=0)
            advance_id = _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=3000,
                deduction_per_payroll=1000,
            )
            conn.execute(
                "UPDATE cash_advances "
                "SET release_confirmation_required=1, released_at=NULL, status='Approved' "
                "WHERE id=?",
                (advance_id,),
            )
            conn.commit()

            def snapshot():
                return _cash_snapshot(
                    conn,
                    run_id=run_id,
                    employee_id=employee_id,
                    period_end="2026-08-31",
                    amount=1000,
                )

            def computed():
                return SimpleNamespace(
                    employee_id=employee_id,
                    sss_ee=0, philhealth_ee=0, pagibig_ee=0, tax=0,
                    other_deductions=0, gross_pay=5000,
                    cash_advance_deduction=0, total_deductions=0, net_pay=5000,
                )

            self.assertEqual(snapshot()["cash_advance_total_available"], 0)
            self.assertEqual(
                _apply_period_cash_advance_deduction(
                    conn, computed(), "2026-08-16", "2026-08-31"
                ).cash_advance_deduction,
                0,
            )

            conn.execute(
                "UPDATE cash_advances SET released_at='2026-09-02' WHERE id=?",
                (advance_id,),
            )
            self.assertEqual(snapshot()["cash_advance_total_available"], 0)

            conn.execute(
                "UPDATE cash_advances SET released_at='2026-08-20' WHERE id=?",
                (advance_id,),
            )
            self.assertEqual(snapshot()["cash_advance_total_available"], 3000)
            self.assertEqual(
                _apply_period_cash_advance_deduction(
                    conn, computed(), "2026-08-16", "2026-08-31"
                ).cash_advance_deduction,
                1000,
            )
        finally:
            conn.close()



    def test_edit_3000_draft_deduction_to_1000_does_not_post_repayment(self) -> None:
        """The exact owner workflow edits net pay but keeps the receivable open."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from api import payroll_adjustments_aggregate
        from api.payroll_adjustments import AdjustmentPayload
        from api.cash_advance_service import calculate_balance

        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "payroll.sqlite"
            conn = get_conn(db_path)
            try:
                init_db(conn)
                ensure_adjustment_schema(conn)
                employee_id = _seed_employee(conn)
                run_id = _seed_run(conn, employee_id, deduction=3000)
                advance_id = _seed_advance(
                    conn,
                    employee_id,
                    advance_date="2026-08-10",
                    amount=3000,
                    deduction_per_payroll=3000,
                )
                conn.execute(
                    "UPDATE payroll_items SET gross_pay=5000, total_deductions=3000, "
                    "net_pay=2000 WHERE payroll_run_id=?",
                    (run_id,),
                )
                conn.execute(
                    "UPDATE cash_advances SET status='Fully Paid' WHERE id=?",
                    (advance_id,),
                )
                conn.commit()
            finally:
                conn.close()

            with (
                patch.object(payroll_adjustments_aggregate, "DB_PATH", db_path),
                patch.object(
                    payroll_adjustments_aggregate,
                    "must_be_payroll_user",
                    return_value={"role_key": "owner", "display_name": "Owner"},
                ),
            ):
                response = payroll_adjustments_aggregate.save_adjustments(
                    run_id,
                    employee_id,
                    AdjustmentPayload(
                        cash_advance_amount=1000,
                        cash_advance_note="Deduct only 1000 this cutoff",
                        expected_version=0,
                    ),
                    authorization="token",
                )

            self.assertTrue(response["ok"])
            conn = get_conn(db_path)
            try:
                item = conn.execute(
                    "SELECT cash_advance_deduction, total_deductions, net_pay "
                    "FROM payroll_items WHERE payroll_run_id=?",
                    (run_id,),
                ).fetchone()
                self.assertEqual(tuple(item), (1000, 1000, 4000))
                self.assertEqual(calculate_balance(conn, advance_id)["balance"], 3000)
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM cash_advance_repayments WHERE cash_advance_id=?",
                        (advance_id,),
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT status FROM payroll_runs WHERE id=?", (run_id,)
                    ).fetchone()[0],
                    "Draft",
                )
            finally:
                conn.close()



if __name__ == "__main__":
    unittest.main()
