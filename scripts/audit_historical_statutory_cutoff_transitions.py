"""Read-only original payroll cutoff-transition comparison.

Never infer agency contribution months, debts, employee refunds, or payments
from cutoff-to-cutoff differences. Historical Paid payroll remains immutable.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import Any

from scripts.audit_historical_statutory_calendar import FIELDS, _centavos, _fields, _programs

BENEFIT_FIELDS = {
    "philhealth": ("philhealth_ee", "philhealth_er"),
    "pagibig": ("pagibig_ee", "pagibig_er"),
}


def _is_current_missing_snapshot(run: Any, snapshot_runs: set[int]) -> bool:
    return (
        str(run["status"]) in {"Paid", "Locked"}
        and run["superseded_by_run_id"] is None
        and int(run["id"]) not in snapshot_runs
    )


def _items(
    conn: sqlite3.Connection, run_id: int
) -> tuple[dict[int, dict[str, int]], set[int], int]:
    employee: dict[int, dict[str, int]] = {}
    duplicated: set[int] = set()
    count = 0
    for row in conn.execute(
        """SELECT employee_id, sss_ee,sss_er,sss_ec,
                  philhealth_ee,philhealth_er,pagibig_ee,pagibig_er
           FROM payroll_items WHERE payroll_run_id=? ORDER BY id""",
        (run_id,),
    ):
        count += 1
        employee_id = int(row["employee_id"])
        if employee_id in employee:
            duplicated.add(employee_id)
            continue
        employee[employee_id] = {field: _centavos(row[field]) for field in FIELDS}
    for employee_id in duplicated:
        employee.pop(employee_id, None)
    return employee, duplicated, count


def audit_historical_statutory_cutoff_transitions(
    conn: sqlite3.Connection, limit: int = 10
) -> dict[str, Any]:
    """Compare the original saved payroll fields around cross-month cutoffs.

    A subsequent same-month run and an earlier cutoff are comparison anchors,
    not evidence that either run represents a legal monthly contribution.
    """
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    conn.row_factory = sqlite3.Row
    snapshot_runs = {
        int(row[0]) for row in conn.execute(
            "SELECT DISTINCT payroll_run_id FROM payroll_statutory_months"
        )
    }
    all_runs = list(conn.execute("""
        SELECT id,status,superseded_by_run_id,period_start,period_end
        FROM payroll_runs ORDER BY period_start,id
    """))
    current: list[tuple[Any, date, date]] = []
    invalid_period_run_ids: list[int] = []
    for run in all_runs:
        if not _is_current_missing_snapshot(run, snapshot_runs):
            continue
        try:
            start = date.fromisoformat(str(run["period_start"]))
            end = date.fromisoformat(str(run["period_end"]))
            if end < start:
                raise ValueError("reversed")
        except ValueError:
            invalid_period_run_ids.append(int(run["id"]))
            continue
        current.append((run, start, end))

    reviews: list[dict[str, Any]] = []
    affected = 0
    ambiguous_successors = 0
    without_successor = 0
    pairs_examined = 0
    for run, start, end in current:
        if (start.year, start.month) == (end.year, end.month):
            continue
        affected += 1
        same_end_month = [
            candidate for candidate in current
            if candidate[0]["id"] != run["id"]
            and candidate[1] > end
            and (candidate[1].year, candidate[1].month) == (end.year, end.month)
        ]
        followups = sorted(same_end_month, key=lambda x: (x[1], int(x[0]["id"])))
        # Exactly one earliest candidate; if there are multiple runs with
        # the identical earliest start date, do not arbitrarily select one.
        if followups:
            first_date = followups[0][1]
            tied = [x for x in followups if x[1] == first_date]
        else:
            tied = []
        if len(tied) > 1:
            ambiguous_successors += 1
            review = {
                "cross_month_run_id": int(run["id"]),
                "cross_month_period": [start.isoformat(), end.isoformat()],
                "status": "ambiguous_following_paid_run",
                "candidate_following_run_ids_sample": [
                    int(c[0]["id"]) for c in tied[:limit]
                ],
            }
            if len(reviews) < limit:
                reviews.append(review)
            continue
        if not tied:
            without_successor += 1
            if len(reviews) < limit:
                reviews.append({
                    "cross_month_run_id": int(run["id"]),
                    "cross_month_period": [start.isoformat(), end.isoformat()],
                    "status": "no_following_paid_run_in_same_month",
                })
            continue
        following, following_start, following_end = tied[0]
        prior_candidates = [
            candidate for candidate in current
            if candidate[2] < start
            and (start - candidate[2]) <= timedelta(days=45)
        ]
        prior = (
            max(prior_candidates, key=lambda x: (x[2], int(x[0]["id"])))
            if prior_candidates else None
        )

        cross_items, cross_duplicates, cross_count = _items(conn, int(run["id"]))
        following_items, following_duplicates, following_count = _items(
            conn, int(following["id"])
        )
        if prior is not None:
            prior_items, prior_duplicates, _ = _items(conn, int(prior[0]["id"]))
        else:
            prior_items, prior_duplicates = {}, set()
        joint_ids = sorted(set(cross_items) & set(following_items))
        comparison_ids = sorted(set(joint_ids) & set(prior_items))
        cross_totals: Counter[str] = Counter()
        follow_totals: Counter[str] = Counter()
        for item in cross_items.values():
            cross_totals.update(item)
        for item in following_items.values():
            follow_totals.update(item)

        zero_then_positive = Counter()
        twice_prior = Counter()
        zero_then_twice_prior = Counter()
        pattern_samples: list[dict[str, Any]] = []
        for employee_id in joint_ids:
            cross = cross_items[employee_id]
            follow = following_items[employee_id]
            prior_fields = prior_items.get(employee_id)
            flags: list[str] = []
            for benefit, names in BENEFIT_FIELDS.items():
                earlier_zero = all(cross[name] == 0 for name in names)
                later_positive = any(follow[name] > 0 for name in names)
                zero_to_positive = earlier_zero and later_positive
                twice = (
                    prior_fields is not None
                    and any(prior_fields[name] > 0 for name in names)
                    and all(
                        abs(follow[name] - 2 * prior_fields[name]) <= 1
                        for name in names
                    )
                )
                if zero_to_positive:
                    zero_then_positive[benefit] += 1
                    flags.append(benefit + "_zero_then_positive")
                if twice:
                    twice_prior[benefit] += 1
                    flags.append(benefit + "_about_twice_preceding_cutoff")
                if zero_to_positive and twice:
                    zero_then_twice_prior[benefit] += 1
            if flags and len(pattern_samples) < limit:
                pattern_samples.append({
                    "employee_id": employee_id,
                    "pattern_flags": flags,
                })
        pairs_examined += 1
        record = {
            "cross_month_run_id": int(run["id"]),
            "cross_month_period": [start.isoformat(), end.isoformat()],
            "following_run_id": int(following["id"]),
            "following_period": [
                following_start.isoformat(), following_end.isoformat()
            ],
            "preceding_reference_run_id": (
                int(prior[0]["id"]) if prior is not None else None
            ),
            "status": "source_pattern_comparison_not_payment_verification",
            "cross_month_payroll_items": cross_count,
            "following_payroll_items": following_count,
            "matched_employee_count": len(joint_ids),
            "matched_with_preceding_run_count": len(comparison_ids),
            "duplicate_employee_item_ids_excluded_count": len(
                cross_duplicates | following_duplicates | prior_duplicates
            ),
            "cross_month_saved_statutory_fields_php": _fields(cross_totals),
            "following_saved_statutory_fields_php": _fields(follow_totals),
            "cross_month_saved_by_program_php": _programs(cross_totals),
            "following_saved_by_program_php": _programs(follow_totals),
            "zero_in_cross_positive_in_follow_employee_counts": dict(
                (name, zero_then_positive[name]) for name in BENEFIT_FIELDS
            ),
            "follow_about_twice_prior_employee_counts": dict(
                (name, twice_prior[name]) for name in BENEFIT_FIELDS
            ),
            "zero_then_about_twice_prior_employee_counts": dict(
                (name, zero_then_twice_prior[name]) for name in BENEFIT_FIELDS
            ),
            "employee_id_pattern_sample": pattern_samples,
            "employee_id_pattern_sample_truncated": any(
                zero_then_positive.values()
            ) and len(pattern_samples) == limit and limit < len(joint_ids),
        }
        if len(reviews) < limit:
            reviews.append(record)

    return {
        "read_only": True,
        "scope": "non_superseded_paid_or_locked_runs_without_monthly_snapshots",
        "cross_month_runs_examined": affected,
        "cross_month_following_pairs_examined": pairs_examined,
        "cross_month_runs_without_following_match": without_successor,
        "ambiguous_following_run_count": ambiguous_successors,
        "invalid_period_run_count": len(invalid_period_run_ids),
        "invalid_period_ids_sample": invalid_period_run_ids[:limit],
        "transition_review_sample": reviews,
        "transition_review_sample_truncated": affected > limit,
        "no_statutory_month_allocations_or_paid_changes": True,
        "not_proof_of_duplicate_deduction": True,
        "not_proof_of_agency_remittance_or_outstanding_liability": True,
        "interpretation": (
            "This comparison observes saved employee statutory fields across "
            "the cross-month cutoff, the next Paid cutoff, and an earlier Paid "
            "reference cutoff. A later amount about twice a preceding cutoff "
            "is a review signal only. It cannot establish the correct monthly "
            "contribution, actual employee withholding or agency payment. "
            "Compare original payslips, dated earnings, benefit enrollment "
            "and agency receipts. No payroll item or agency ledger is modified."
        ),
    }
