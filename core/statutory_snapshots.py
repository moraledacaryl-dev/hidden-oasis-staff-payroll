from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from .money import money


def ensure_statutory_snapshot_schema(conn: Any) -> None:
    """Create the immutable per-run/per-employee/per-month statutory ledger."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_statutory_months (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            month_start TEXT NOT NULL,
            gross_pay REAL NOT NULL DEFAULT 0,
            sss_ee REAL NOT NULL DEFAULT 0,
            philhealth_ee REAL NOT NULL DEFAULT 0,
            pagibig_ee REAL NOT NULL DEFAULT 0,
            sss_er REAL NOT NULL DEFAULT 0,
            sss_ec REAL NOT NULL DEFAULT 0,
            philhealth_er REAL NOT NULL DEFAULT 0,
            pagibig_er REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(payroll_run_id, employee_id, month_start)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_payroll_statutory_months_employee_month ON payroll_statutory_months(employee_id, month_start)"
    )


def replace_run_employee_snapshots(
    conn: Any,
    payroll_run_id: int,
    employee_id: int,
    snapshots: Mapping[date, Mapping[str, float]],
) -> None:
    """Replace snapshots only while the owning payroll draft itself is replaced."""
    ensure_statutory_snapshot_schema(conn)
    conn.execute(
        "DELETE FROM payroll_statutory_months WHERE payroll_run_id=? AND employee_id=?",
        (payroll_run_id, employee_id),
    )
    for month_start, values in sorted(snapshots.items()):
        conn.execute(
            """
            INSERT INTO payroll_statutory_months(
                payroll_run_id, employee_id, month_start, gross_pay,
                sss_ee, philhealth_ee, pagibig_ee, sss_er, sss_ec,
                philhealth_er, pagibig_er
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payroll_run_id,
                employee_id,
                month_start.isoformat(),
                money(values.get("gross_pay", 0)),
                money(values.get("sss_ee", 0)),
                money(values.get("philhealth_ee", 0)),
                money(values.get("pagibig_ee", 0)),
                money(values.get("sss_er", 0)),
                money(values.get("sss_ec", 0)),
                money(values.get("philhealth_er", 0)),
                money(values.get("pagibig_er", 0)),
            ),
        )


def previous_month_snapshot_totals(
    conn: Any,
    employee_id: int,
    month_start: date,
    before_date: date,
) -> dict[str, float]:
    """Read authoritative settled snapshots before a date within one month."""
    ensure_statutory_snapshot_schema(conn)
    run_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(payroll_runs)").fetchall()}
    superseded_filter = ""
    if "superseded_by_run_id" in run_columns:
        superseded_filter = " AND pr.superseded_by_run_id IS NULL"
    rows = conn.execute(
        f"""
        SELECT sm.*
        FROM payroll_statutory_months sm
        JOIN payroll_runs pr ON pr.id=sm.payroll_run_id
        WHERE sm.employee_id=?
          AND sm.month_start=?
          AND pr.period_start < ?
          AND pr.status IN ('For Owner Review','Reviewed','Approved','Paid','Locked')
          {superseded_filter}
        """,
        (employee_id, month_start.isoformat(), before_date.isoformat()),
    ).fetchall()

    def total(column: str) -> float:
        return sum(float(row[column] or 0) for row in rows)

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
