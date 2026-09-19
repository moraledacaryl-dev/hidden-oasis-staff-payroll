from __future__ import annotations

from datetime import date
from typing import Any


HISTORY_STATUSES = (
    "For Owner Review",
    "Reviewed",
    "Approved",
    "Paid",
    "Locked",
)


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def month_previous_contribs(
    conn: Any,
    employee_id: int,
    month_start: date,
    before_date: date,
) -> dict[str, float]:
    """Return settled contribution history before a date in one calendar month.

    Replacement payroll runs must not be counted together with the run they
    supersede. Draft runs are deliberately excluded: a draft is not evidence
    that a statutory deduction was actually withheld.
    """
    superseded_filter = ""
    if "superseded_by_run_id" in _columns(conn, "payroll_runs"):
        superseded_filter = " AND pr.superseded_by_run_id IS NULL"

    placeholders = ",".join("?" for _ in HISTORY_STATUSES)
    rows = conn.execute(
        f"""
        SELECT
            pi.gross_pay,
            pi.sss_ee,
            pi.philhealth_ee,
            pi.pagibig_ee,
            COALESCE(pi.sss_er,0) AS sss_er,
            COALESCE(pi.sss_ec,0) AS sss_ec,
            COALESCE(pi.philhealth_er,0) AS philhealth_er,
            COALESCE(pi.pagibig_er,0) AS pagibig_er
        FROM payroll_items pi
        JOIN payroll_runs pr ON pr.id=pi.payroll_run_id
        WHERE pi.employee_id=?
          AND pr.period_start >= ?
          AND pr.period_end < ?
          AND pr.status IN ({placeholders})
          {superseded_filter}
        """,
        (
            employee_id,
            month_start.isoformat(),
            before_date.isoformat(),
            *HISTORY_STATUSES,
        ),
    ).fetchall()

    def total(key: str) -> float:
        return sum(float(row[key] or 0) for row in rows)

    return {
        "gross": total("gross_pay"),
        "sss": total("sss_ee"),
        "philhealth": total("philhealth_ee"),
        "pagibig": total("pagibig_ee"),
        "sss_er": total("sss_er"),
        "sss_ec": total("sss_ec"),
        "philhealth_er": total("philhealth_er"),
        "pagibig_er": total("pagibig_er"),
    }
