"""Read-only carry-forward for finalized legacy first-half payrolls.

Legacy operational first-half cutoffs include the previous month's last day
(e.g. 2026-09-30 through 2026-10-14). Before the monthly-snapshot migration,
their already-Paid item deductions were stored only on payroll_items. The
current calculator otherwise sees zero previously withheld amounts and
reapplies the full month's contributions in the second cutoff.

Only recognize an intact, *finalized* legacy first-half run with no statutory
snapshots for that employee in any month. Existing item values are evidence;
never recalculate or mutate the Paid run. Payrolls with ambiguous/partial
history, Draft/Approved statuses, or nonstandard periods keep the usual
missing-history review gate.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .money import money


def legacy_paid_first_half_evidence(
    conn: Any,
    employee_id: int,
    month_start: date,
    before_date: date,
) -> dict[str, float | int] | None:
    """Return existing withheld amounts for one legacy cross-month Paid cutoff.

    The payroll's configured policy attributes these existing employee and
    employer contributions to the *cutoff-ending* month. Its original gross is
    retained as the previously used cutoff basis for SSS catch-up; it is NOT a
    reconstruction of dated work or a modification of an agency remittance.
    """
    if month_start.day != 1 or before_date <= month_start.replace(day=14):
        return None
    required_tables = ("payroll_runs", "payroll_items", "payroll_statutory_months")
    if any(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is None
        for name in required_tables
    ):
        return None

    run_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(payroll_runs)")}
    superseded = (
        "AND pr.superseded_by_run_id IS NULL"
        if "superseded_by_run_id" in run_columns
        else ""
    )
    cutoff_start = month_start - timedelta(days=1)
    cutoff_end = month_start.replace(day=14)
    rows = conn.execute(
        f"""
        SELECT pr.id, pi.gross_pay,
               pi.sss_ee, pi.philhealth_ee, pi.pagibig_ee,
               COALESCE(pi.sss_er,0) AS sss_er,
               COALESCE(pi.sss_ec,0) AS sss_ec,
               COALESCE(pi.philhealth_er,0) AS philhealth_er,
               COALESCE(pi.pagibig_er,0) AS pagibig_er
        FROM payroll_items pi
        JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
        WHERE pi.employee_id=?
          AND pr.period_start=?
          AND pr.period_end=?
          AND pr.period_end < ?
          AND pr.status IN ('Paid','Locked')
          {superseded}
          AND NOT EXISTS (
            SELECT 1 FROM payroll_statutory_months sm
            WHERE sm.payroll_run_id=pr.id AND sm.employee_id=pi.employee_id
          )
        """,
        (employee_id, cutoff_start.isoformat(), cutoff_end.isoformat(), before_date.isoformat()),
    ).fetchall()
    if len(rows) > 1:
        raise ValueError(
            "Multiple finalized first-half payrolls lack statutory history; "
            "reconcile the original runs before calculating later payroll."
        )
    if not rows:
        return None
    row = rows[0]
    fields = {
        "gross": "gross_pay",
        "sss": "sss_ee",
        "philhealth": "philhealth_ee",
        "pagibig": "pagibig_ee",
        "sss_er": "sss_er",
        "sss_ec": "sss_ec",
        "philhealth_er": "philhealth_er",
        "pagibig_er": "pagibig_er",
    }
    result: dict[str, float | int] = {"run_id": int(row[0])}
    for output_key, column in fields.items():
        # sqlite3.Row has name access; other callers may return mappings.
        value = money(float(row[column] or 0))
        if value < 0:
            raise ValueError("Negative legacy statutory withholding needs manual reconciliation")
        result[output_key] = value
    return result
