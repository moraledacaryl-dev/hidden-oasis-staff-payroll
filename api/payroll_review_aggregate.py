from __future__ import annotations

from typing import Any

from core.db import fetchall
from core.money import money


def _rows_by_employee(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        employee_id = int(row.get("employee_id") or 0)
        grouped.setdefault(employee_id, []).append(row)
    return grouped


def _recompute_summary(result: dict[str, Any]) -> dict[str, Any]:
    rows = list(result.get("rows") or [])
    result["expected_total"] = money(
        sum(float(row.get("expected") or 0) for row in rows)
    )
    result["applied_total"] = money(
        sum(float(row.get("applied") or 0) for row in rows)
    )
    issue_statuses = {"PARTIAL", "OVER", "NOT APPLIED", "UNALLOCATED"}
    result["issue_count"] = sum(
        1 for row in rows if str(row.get("status") or "") in issue_statuses
    )
    result["status"] = "OK" if result["issue_count"] == 0 else "Needs Review"
    return result


def _mark_employee_mismatch(
    employee_rows: list[dict[str, Any]],
    *,
    expected_total: float,
    applied_total: float,
) -> None:
    delta = money(applied_total - expected_total)
    if abs(delta) < 0.005:
        return
    candidates = [
        row
        for row in employee_rows
        if "manual" not in str(row.get("repayment_method") or "").lower()
    ]
    if not candidates:
        return
    target = next(
        (row for row in candidates if float(row.get("applied") or 0) > 0),
        candidates[0],
    )
    target["status"] = "OVER" if delta > 0 else "PARTIAL"


def normalize_cash_advance_run_check(
    conn: Any,
    run_id: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Make payroll review follow the authoritative employee-level deduction.

    Configured per-cutoff amounts are edit-time suggestions only. Once a Draft
    contains an explicit employee-level cash-advance deduction, review must
    allocate that amount across eligible advances FIFO without re-capping each
    advance at its suggestion. For paid runs, posted repayment rows are the
    authoritative allocation and are reconciled back to the payroll-item total.
    """
    rows = list(result.get("rows") or [])
    if not rows:
        return _recompute_summary(result)

    payroll_items = fetchall(
        conn,
        """
        SELECT employee_id, COALESCE(cash_advance_deduction,0) AS deduction
        FROM payroll_items
        WHERE payroll_run_id=?
        """,
        (run_id,),
    )
    deduction_by_employee = {
        int(row.get("employee_id") or 0): money(row.get("deduction") or 0)
        for row in payroll_items
    }
    grouped = _rows_by_employee(rows)

    if str(result.get("source") or "") == "posted_repayments":
        for employee_id, employee_rows in grouped.items():
            for row in employee_rows:
                if "manual" in str(row.get("repayment_method") or "").lower():
                    row["expected"] = 0.0
                    row["applied"] = 0.0
                    row["status"] = "MANUAL REPAYMENT"
                    continue
                applied = money(row.get("applied") or 0)
                row["expected"] = applied
                row["status"] = "APPLIED" if applied > 0 else "NOT SELECTED"
            posted_total = money(
                sum(float(row.get("applied") or 0) for row in employee_rows)
            )
            _mark_employee_mismatch(
                employee_rows,
                expected_total=deduction_by_employee.get(employee_id, 0.0),
                applied_total=posted_total,
            )
        return _recompute_summary(result)

    explicit_rows = fetchall(
        conn,
        """
        SELECT employee_id, cash_advance_id, COALESCE(cash_advance_amount,0) AS amount
        FROM payroll_item_adjustments
        WHERE payroll_run_id=?
          AND cash_advance_id IS NOT NULL
          AND COALESCE(cash_advance_amount,0)>0
        """,
        (run_id,),
    )
    explicit_by_employee: dict[int, float] = {}
    explicit_ids: set[int] = set()
    for row in explicit_rows:
        employee_id = int(row.get("employee_id") or 0)
        advance_id = int(row.get("cash_advance_id") or 0)
        explicit_ids.add(advance_id)
        explicit_by_employee[employee_id] = money(
            explicit_by_employee.get(employee_id, 0.0)
            + money(row.get("amount") or 0)
        )

    for employee_id, employee_rows in grouped.items():
        remaining = money(
            max(
                0.0,
                deduction_by_employee.get(employee_id, 0.0)
                - explicit_by_employee.get(employee_id, 0.0),
            )
        )
        automatic_rows: list[dict[str, Any]] = []
        for row in employee_rows:
            advance_id = int(row.get("cash_advance_id") or 0)
            if "manual" in str(row.get("repayment_method") or "").lower():
                row["expected"] = 0.0
                row["applied"] = 0.0
                row["status"] = "MANUAL REPAYMENT"
                continue
            if advance_id in explicit_ids:
                continue
            automatic_rows.append(row)
            available = money(max(0.0, float(row.get("balance_before_run") or 0)))
            applied = money(min(remaining, available)) if remaining > 0 else 0.0
            row["applied"] = applied
            row["expected"] = applied
            row["balance_after_run"] = money(max(0.0, available - applied))
            row["status"] = "APPLIED" if applied > 0 else "NOT SELECTED"
            remaining = money(max(0.0, remaining - applied))

        if remaining > 0.005 and automatic_rows:
            automatic_rows[-1]["status"] = "UNALLOCATED"

    return _recompute_summary(result)


def install_aggregate_cash_advance_review(payroll_review_module: Any) -> None:
    current = payroll_review_module._cash_advance_run_check
    if getattr(current, "_aggregate_cash_review", False):
        return

    def wrapped(
        conn: Any,
        run_id: int,
        period_start: str,
        period_end: str,
    ) -> dict[str, Any]:
        result = current(conn, run_id, period_start, period_end)
        return normalize_cash_advance_run_check(conn, run_id, result)

    wrapped._aggregate_cash_review = True  # type: ignore[attr-defined]
    payroll_review_module._cash_advance_run_check = wrapped
