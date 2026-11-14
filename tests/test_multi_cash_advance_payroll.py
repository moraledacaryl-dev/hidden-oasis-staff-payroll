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
    stamp = now_iso()
    cursor = conn.execute(
        """
        INSERT INTO payroll_runs(
            period_start,period_end,payout_date,run_label,status,created_at
        ) VALUES('2026-08-16',?,'2026-09-01','Test','Draft',?)
        """,
        (period_end, stamp),
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

            self.assertEqual(snapshot["cash_advance_reserved_elsewhere"], 50)
            self.assertEqual(snapshot["cash_advance_total_available"], 250)
            self.assertEqual(snapshot["cash_advance_suggested"], 150)
            self.assertEqual(
                snapshot["cash_advance_allocations"],
                [
                    {
                        "cash_advance_id": first,
                        "advance_date": "2026-08-01",
                        "reason": None,
                        "available_balance": 50.0,
                        "amount": 50.0,
                    },
                    {
                        "cash_advance_id": second,
                        "advance_date": "2026-08-10",
                        "reason": None,
                        "available_balance": 200.0,
                        "amount": 130.0,
                    },
                ],
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
            current_run_id = _seed_run(conn, employee_id, deduction=0)
            _seed_advance(
                conn,
                employee_id,
                advance_date="2026-08-10",
                amount=3000,
                deduction_per_payroll=3000,
            )
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
                period_end="2026-08-31",
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
                    cash_advance_id,employee_id,repayment_date,amount,source,active
                ) VALUES(?,?,?,3000,'Manual',1)
                """,
                (advance_id, employee_id, "2026-08-20"),
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



if __name__ == "__main__":
    unittest.main()
