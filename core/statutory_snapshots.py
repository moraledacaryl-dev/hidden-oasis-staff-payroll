from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from .money import money
from .statutory_legacy_history import legacy_paid_first_half_evidence


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


STATUTORY_MONEY_COLUMNS = (
    "sss_ee", "sss_er", "sss_ec",
    "philhealth_ee", "philhealth_er", "pagibig_ee", "pagibig_er",
)


def assert_prior_month_statutory_coverage(
    conn: Any,
    run_id: int,
    employee_id: int,
    period_start: str,
    period_end: str,
) -> None:
    """Avoid applying MTD contribution targets over missing prior paid evidence.

    Prior non-superseded, non-Draft payrolls that overlap a contribution month
    must have a snapshot for this employee/month. Missing history is a review
    gate, never permission to recreate or mutate Paid payroll.
    """
    from .statutory_periods import calendar_month_segments

    # Production startup initializes this table; direct Draft API/test
    # invocation must also be safe before a prior-month coverage query.
    ensure_statutory_snapshot_schema(conn)
    run_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(payroll_runs)")
    }
    current_filter = (
        "AND COALESCE(pr.superseded_by_run_id,0)=0"
        if "superseded_by_run_id" in run_columns else ""
    )
    for segment in calendar_month_segments(period_start, period_end):
        earlier = conn.execute(
            f"""
            SELECT pr.id
            FROM payroll_runs pr
            JOIN payroll_items pi ON pi.payroll_run_id=pr.id
            WHERE pi.employee_id=?
              AND pr.id<>?
              AND pr.status IN ('For Owner Review','Reviewed','Approved','Paid','Locked')
              {current_filter}
              AND date(pr.period_start) < date(?)
              AND date(pr.period_start) <= date(?)
              AND date(pr.period_end) >= date(?)
              AND NOT EXISTS(
                  SELECT 1 FROM payroll_statutory_months sm
                  WHERE sm.payroll_run_id=pr.id
                    AND sm.employee_id=pi.employee_id
                    AND sm.month_start=?
              )
            ORDER BY pr.period_start, pr.id
            """,
            (
                employee_id, run_id, segment.start.isoformat(),
                segment.month_end.isoformat(), segment.month_start.isoformat(),
                segment.month_start.isoformat(),
            ),
        ).fetchall()
        # A historically Paid operational first-half (previous month's final
        # day through this month's 14th) predates the snapshot migration.
        # Its intact payroll item is reliable *withholding* evidence without
        # modifying it; all other missing histories still block the Draft.
        legacy = legacy_paid_first_half_evidence(
            conn, employee_id, segment.month_start, segment.start
        )
        for earlier_run in earlier:
            if legacy is not None and int(earlier_run[0]) == int(legacy["run_id"]):
                continue
            raise ValueError(
                "Earlier payroll run #"
                + str(earlier_run[0])
                + " lacks a statutory snapshot for "
                + segment.month_start.isoformat()[:7]
                + "; reconcile original payroll evidence before creating a later Draft"
            )


def persist_computed_draft_snapshots(
    conn: Any,
    run_id: int,
    result: Any,
    period_start: str,
    period_end: str,
) -> None:
    """Persist exactly the dated snapshots calculated for a new or recalculated Draft.

    Reject incomplete, inconsistent or undated snapshots instead of inventing a
    calendar-month split. Run state and source-item validation happen before
    replacing any snapshot rows. The outer payroll transaction owns commit/rollback.
    """
    from .statutory_periods import calendar_month_segments

    run = conn.execute("SELECT status FROM payroll_runs WHERE id=?", (run_id,)).fetchone()
    if run is None or str(run[0]) != "Draft":
        raise ValueError("Statutory snapshots can only be replaced for a Draft payroll run")

    snapshots = getattr(result, "_statutory_snapshots", None)
    if not isinstance(snapshots, Mapping):
        raise ValueError("Draft payroll calculation is missing dated statutory snapshots")

    assert_prior_month_statutory_coverage(
        conn, run_id, int(result.employee_id), period_start, period_end
    )
    expected_months = {segment.month_start for segment in calendar_month_segments(period_start, period_end)}
    if set(snapshots) != expected_months:
        raise ValueError("Draft statutory snapshots must match the exact cutoff calendar months")

    fields = ("gross_pay", *STATUTORY_MONEY_COLUMNS)
    try:
        for field in fields:
            expected = money(getattr(result, field))
            actual = money(sum(money(values.get(field, 0)) for values in snapshots.values()))
            if abs(expected - actual) > 0.01:
                raise ValueError(
                    f"Draft statutory {field} does not reconcile to saved payroll item"
                )
    except (TypeError, AttributeError, ArithmeticError) as exc:
        raise ValueError("Draft statutory snapshots contain invalid money values") from exc

    replace_run_employee_snapshots(
        conn, run_id, int(result.employee_id), snapshots
    )


def previous_month_snapshot_totals(
    conn: Any,
    employee_id: int,
    month_start: date,
    before_date: date,
) -> dict[str, float]:
    """Read authoritative settled snapshots before a date within one month."""
    # Read paths must remain side-effect free. Schema creation belongs to startup/migrations.
    snapshot_table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='payroll_statutory_months'"
    ).fetchone()
    if snapshot_table_exists is None:
        return {
            "gross": 0.0,
            "sss": 0.0,
            "philhealth": 0.0,
            "pagibig": 0.0,
            "sss_er": 0.0,
            "sss_ec": 0.0,
            "philhealth_er": 0.0,
            "pagibig_er": 0.0,
        }
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

    # Historical Paid cross-month first halves had no monthly snapshot table.
    # Deduct exactly what was recorded as withheld on the already-Paid item,
    # instead of charging the employee the full monthly contribution again.
    # The compatibility source is deliberately narrower than general history.
    legacy = legacy_paid_first_half_evidence(
        conn, employee_id, month_start, before_date
    )
    legacy = legacy or {}
    return {
        "gross": money(total("gross_pay") + float(legacy.get("gross", 0))),
        "sss": money(total("sss_ee") + float(legacy.get("sss", 0))),
        "philhealth": money(total("philhealth_ee") + float(legacy.get("philhealth", 0))),
        "pagibig": money(total("pagibig_ee") + float(legacy.get("pagibig", 0))),
        "sss_er": money(total("sss_er") + float(legacy.get("sss_er", 0))),
        "sss_ec": money(total("sss_ec") + float(legacy.get("sss_ec", 0))),
        "philhealth_er": money(total("philhealth_er") + float(legacy.get("philhealth_er", 0))),
        "pagibig_er": money(total("pagibig_er") + float(legacy.get("pagibig_er", 0))),
    }
