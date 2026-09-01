from __future__ import annotations

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


def test_aggregate_snapshot_spans_multiple_advances_and_respects_other_drafts() -> None:
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

        assert snapshot["cash_advance_reserved_elsewhere"] == 50
        assert snapshot["cash_advance_total_available"] == 250
        assert snapshot["cash_advance_suggested"] == 150
        assert snapshot["cash_advance_allocations"] == [
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
        ]
    finally:
        conn.close()


def test_paid_payroll_deduction_posts_across_multiple_advances_fifo() -> None:
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
        assert [(int(row[0]), float(row[1])) for row in rows] == [
            (first, 100.0),
            (second, 150.0),
        ]
        assert all(int(row[0]) != future for row in rows)
    finally:
        conn.close()
