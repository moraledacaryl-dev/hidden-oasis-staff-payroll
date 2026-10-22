"""Read-only calendar coverage buckets for historical Paid statutory item evidence.

This report is not an agency contribution-month ledger. A payroll period that
crosses a month boundary remains in a separate unallocated bucket even when
the payroll calculation used an operational deduction-month convention.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

FIELDS = (
    "sss_ee", "sss_er", "sss_ec",
    "philhealth_ee", "philhealth_er",
    "pagibig_ee", "pagibig_er",
)
PROGRAMS = {
    "sss": ("sss_ee", "sss_er", "sss_ec"),
    "philhealth": ("philhealth_ee", "philhealth_er"),
    "pagibig": ("pagibig_ee", "pagibig_er"),
}


def _centavos(value: Any) -> int:
    try:
        decimal = Decimal(str(value if value is not None else 0))
        if not decimal.is_finite():
            raise ValueError("non-finite statutory amount")
        return int((decimal * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid saved statutory monetary value") from exc


def _fields(centavos: Counter[str]) -> dict[str, float]:
    return {name: centavos[name] / 100 for name in FIELDS}


def _programs(centavos: Counter[str]) -> dict[str, float]:
    return {
        program: sum(centavos[field] for field in fields) / 100
        for program, fields in PROGRAMS.items()
    }


def audit_historical_paid_statutory_calendar_buckets(
    conn: sqlite3.Connection, limit: int = 10
) -> dict[str, Any]:
    """Bucket historical saved values by covered calendar dates, never remittances.

    Scope matches the existing historical item audit: only current Paid/Locked
    runs with payroll items and no statutory monthly snapshots. A single-month
    cutoff is a date-coverage classification, NOT an agency contribution month.
    """
    if limit < 0:
        raise ValueError("limit cannot be negative")

    grand: Counter[str] = Counter()
    allocated: Counter[str] = Counter()
    uncertain: Counter[str] = Counter()
    buckets: dict[str, dict[str, Any]] = {}
    exceptions: list[dict[str, Any]] = []
    run_count = 0
    item_count = 0
    cross_month_count = 0
    invalid_period_count = 0
    invalid_sample: list[int] = []

    for run in conn.execute("""
        SELECT pr.id, pr.period_start, pr.period_end
        FROM payroll_runs pr
        WHERE pr.status IN ('Paid','Locked')
          AND COALESCE(pr.superseded_by_run_id,0)=0
          AND EXISTS(
              SELECT 1 FROM payroll_items pi WHERE pi.payroll_run_id=pr.id
          )
          AND NOT EXISTS(
              SELECT 1 FROM payroll_statutory_months sm WHERE sm.payroll_run_id=pr.id
          )
        ORDER BY pr.id
    """):
        run_id = int(run["id"])
        run_count += 1
        subtotal: Counter[str] = Counter()
        rows = 0
        for item in conn.execute("""
            SELECT sss_ee,sss_er,sss_ec,philhealth_ee,philhealth_er,
                   pagibig_ee,pagibig_er
            FROM payroll_items WHERE payroll_run_id=? ORDER BY id
        """, (run_id,)):
            rows += 1
            item_count += 1
            for field in FIELDS:
                value = _centavos(item[field])
                subtotal[field] += value
                grand[field] += value

        period_start = str(run["period_start"] or "")
        period_end = str(run["period_end"] or "")
        try:
            start = date.fromisoformat(period_start)
            end = date.fromisoformat(period_end)
            if end < start:
                raise ValueError("reversed payroll period")
        except ValueError:
            invalid_period_count += 1
            if len(invalid_sample) < limit:
                invalid_sample.append(run_id)
            uncertain.update(subtotal)
            if len(exceptions) < limit:
                exceptions.append({
                    "payroll_run_id": run_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "reason": "invalid_period_dates",
                    "payroll_items": rows,
                    "saved_statutory_fields_php": _fields(subtotal),
                    "saved_combined_by_program_php": _programs(subtotal),
                })
            continue

        if (start.year, start.month) != (end.year, end.month):
            cross_month_count += 1
            uncertain.update(subtotal)
            if len(exceptions) < limit:
                exceptions.append({
                    "payroll_run_id": run_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "reason": "spans_multiple_calendar_months",
                    "payroll_items": rows,
                    "saved_statutory_fields_php": _fields(subtotal),
                    "saved_combined_by_program_php": _programs(subtotal),
                })
            continue

        month = start.strftime("%Y-%m")
        if month not in buckets:
            buckets[month] = {
                "money": Counter(), "run_count": 0, "item_count": 0,
                "run_ids_sample": [],
            }
        bucket = buckets[month]
        bucket["money"].update(subtotal)
        bucket["run_count"] += 1
        bucket["item_count"] += rows
        if len(bucket["run_ids_sample"]) < limit:
            bucket["run_ids_sample"].append(run_id)
        allocated.update(subtotal)

    # Centavo-level reconciliation must never silently drop a payroll period.
    if any(
        grand[field] != allocated[field] + uncertain[field]
        for field in FIELDS
    ):
        raise RuntimeError("historical statutory calendar buckets do not reconcile")

    return {
        "scope": "current_paid_or_locked_runs_missing_all_monthly_snapshots",
        "report_classification": "payroll_period_calendar_coverage_not_agency_contribution_month",
        "read_only": True,
        "no_monthly_snapshot_backfill": True,
        "official_contribution_months_not_inferred": True,
        "affected_run_count": run_count,
        "affected_payroll_items": item_count,
        "single_calendar_month_buckets": [
            {
                "calendar_coverage_month": month,
                "payroll_runs": bucket["run_count"],
                "payroll_items": bucket["item_count"],
                "run_ids_sample": bucket["run_ids_sample"],
                "run_ids_sample_truncated": bucket["run_count"] > limit,
                "saved_statutory_fields_php": _fields(bucket["money"]),
                "saved_combined_by_program_php": _programs(bucket["money"]),
            }
            for month, bucket in sorted(buckets.items())
        ],
        "cross_month_run_count": cross_month_count,
        "invalid_period_run_count": invalid_period_count,
        "invalid_period_run_ids_sample": invalid_sample,
        "unallocated_periods_sample": exceptions,
        "unallocated_periods_sample_truncated": (
            cross_month_count + invalid_period_count > limit
        ),
        "single_month_covered_saved_fields_php": _fields(allocated),
        "cross_month_or_invalid_unallocated_saved_fields_php": _fields(uncertain),
        "all_in_scope_saved_fields_php": _fields(grand),
        "all_in_scope_saved_combined_by_program_php": _programs(grand),
        "reconciles_to_all_source_items_centavo_exact": True,
        "interpretation": (
            "These month buckets group paid payroll items by the dates covered "
            "by each cutoff, not their legally designated agency contribution month. "
            "Cross-month cutoffs and malformed periods remain unallocated. "
            "No snapshot rows, official liabilities, agency remittances, "
            "Accounting entries or payroll balances are created or changed. "
            "Compare to original payslips, benefit settings at the time, dated "
            "earning detail and external official agency receipts."
        ),
    }
