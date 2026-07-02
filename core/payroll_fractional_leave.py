from __future__ import annotations

from typing import Any

from core.db import fetchall, fetchone, get_setting
from core.payroll_leave_days import paid_leave_days_for_cutoff


def _active_employee(conn: Any, employee_id: int) -> dict[str, Any] | None:
    return fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,))


def _is_credit_balance_warning(message: str) -> bool:
    text = str(message or "")
    return (
        (text.startswith("Approved paid leave '") and "entitlement is not enabled" in text)
        or (text.startswith("Leave '") and "usage exceeds configured credits" in text)
        or (text.startswith("Paid leave '") and "unique day(s)" in text)
        or text.startswith("Paid leave was prorated")
    )


def _preview_warnings(warnings: list[str] | None) -> list[str]:
    return [warning for warning in (warnings or []) if not _is_credit_balance_warning(warning)]


def _correct_paid_leave_days(conn: Any, employee_id: int, period_start: str, period_end: str) -> float:
    rows = fetchall(
        conn,
        """
        SELECT lr.*, lt.paid, lt.name AS leave_name
        FROM leave_requests lr
        JOIN leave_types lt ON lt.id=lr.leave_type_id
        WHERE lr.employee_id=? AND lr.status='Approved'
          AND lr.start_date <= ? AND lr.end_date >= ?
        ORDER BY lr.start_date, lr.id
        """,
        (employee_id, period_end, period_start),
    )
    paid_dates: set[str] = set()
    total = 0.0
    for row in rows:
        if not int(row.get("paid") or 0):
            continue
        days, dates = paid_leave_days_for_cutoff(row, period_start, period_end, paid_dates)
        if days <= 0:
            continue
        total += days
        paid_dates.update(dates)
    return round(total, 4)


def _recompute_statutory_and_net(conn: Any, result: Any, emp: dict[str, Any], period_start: str) -> None:
    # Import here to avoid changing payroll_engine import order.
    from core.payroll_engine import compute_semi_monthly_withholding_tax, get_month_previous_contribs, get_sss_share, parse_date

    result.gross_pay = round(
        result.regular_pay
        + result.ot_pay
        + result.night_diff_pay
        + result.holiday_pay
        + result.paid_leave_pay
        + result.freelance_pay
        + result.other_earnings,
        2,
    )

    result.sss_ee = result.sss_er = result.sss_ec = 0.0
    result.philhealth_ee = result.philhealth_er = 0.0
    result.pagibig_ee = result.pagibig_er = 0.0
    result.tax = 0.0

    prev = get_month_previous_contribs(conn, int(emp["id"]), period_start)
    declared = float(emp.get("declared_monthly_base") or 0)
    has_current_gross = result.gross_pay > 0.005

    if has_current_gross and int(emp.get("benefits_sss") or 0):
        month_gross_basis = prev["gross"] + result.gross_pay
        sss_month_ee, sss_month_er, sss_month_ec = get_sss_share(conn, month_gross_basis)
        result.sss_ee = round(max(0.0, sss_month_ee - prev["sss"]), 2)
        result.sss_er = round(max(0.0, sss_month_er - prev["sss_er"]), 2)
        result.sss_ec = round(max(0.0, sss_month_ec - prev["sss_ec"]), 2)

    if has_current_gross and int(emp.get("benefits_philhealth") or 0):
        ph_rate = float(get_setting(conn, "philhealth_rate", "0.05") or 0.05)
        ph_floor = float(get_setting(conn, "philhealth_floor", "10000") or 10000)
        ph_ceiling = float(get_setting(conn, "philhealth_ceiling", "100000") or 100000)
        ph_base = min(max(declared, ph_floor), ph_ceiling)
        ph_month_total = ph_base * ph_rate
        if parse_date(period_start).day <= 15:
            result.philhealth_ee = round(ph_month_total / 4.0, 2)
            result.philhealth_er = round(ph_month_total / 4.0, 2)
        else:
            result.philhealth_ee = round(max(0.0, (ph_month_total / 2.0) - prev["philhealth"]), 2)
            result.philhealth_er = round(max(0.0, (ph_month_total / 2.0) - prev["philhealth_er"]), 2)

    if has_current_gross and int(emp.get("benefits_pagibig") or 0):
        pi_rate = float(get_setting(conn, "pagibig_rate", "0.02") or 0.02)
        pi_er_rate = float(get_setting(conn, "pagibig_employer_rate", "0.02") or 0.02)
        pi_ceiling = float(get_setting(conn, "pagibig_ceiling", "10000") or 10000)
        pi_base = min(declared, pi_ceiling)
        pi_month_ee = pi_base * pi_rate
        pi_month_er = pi_base * pi_er_rate
        if parse_date(period_start).day <= 15:
            result.pagibig_ee = round(pi_month_ee / 2.0, 2)
            result.pagibig_er = round(pi_month_er / 2.0, 2)
        else:
            result.pagibig_ee = round(max(0.0, pi_month_ee - prev["pagibig"]), 2)
            result.pagibig_er = round(max(0.0, pi_month_er - prev["pagibig_er"]), 2)

    if has_current_gross and int(emp.get("benefits_tax") or 0):
        taxable_comp = result.gross_pay - result.sss_ee - result.philhealth_ee - result.pagibig_ee
        result.tax = compute_semi_monthly_withholding_tax(taxable_comp)

    statutory_and_manual = result.sss_ee + result.philhealth_ee + result.pagibig_ee + result.tax + result.other_deductions
    ca_capacity = max(0.0, result.gross_pay - statutory_and_manual)
    ca_rows = fetchall(
        conn,
        """
        SELECT * FROM cash_advances
        WHERE employee_id=? AND outstanding_balance > 0
          AND status IN ('Released','Partially Paid','Approved')
        ORDER BY request_date, id
        """,
        (emp["id"],),
    )
    ca_deduction = 0.0
    for ca in ca_rows:
        raw = ca.get("custom_next_deduction")
        scheduled = float(raw) if raw not in (None, "") else float(ca.get("repayment_per_cutoff") or 0)
        if scheduled <= 0 or ca_capacity <= ca_deduction:
            continue
        amount = min(float(ca["outstanding_balance"]), scheduled, ca_capacity - ca_deduction)
        ca_deduction += amount
    result.cash_advance_deduction = round(ca_deduction, 2)
    result.total_deductions = round(statutory_and_manual + result.cash_advance_deduction, 2)
    result.net_pay = round(result.gross_pay - result.total_deductions, 2)


def apply_fractional_paid_leave_adjustment(conn: Any, result: Any, period_start: str, period_end: str) -> Any:
    """Correct payroll output when approved paid leave uses fractional stored days."""
    employee_id = int(result.employee_id)
    emp = _active_employee(conn, employee_id)
    if not emp:
        return result

    result.warnings = _preview_warnings(result.warnings)
    corrected_days = _correct_paid_leave_days(conn, employee_id, period_start, period_end)
    standard_paid_hours = float(get_setting(conn, "standard_daily_paid_hours", "8") or 8)
    hourly_rate = float(emp.get("hourly_rate") or 0)
    old_pay = float(result.paid_leave_pay or 0)

    result.paid_leave_days = round(corrected_days, 4)
    result.paid_leave_pay = round(corrected_days * standard_paid_hours * hourly_rate, 2)
    if abs(old_pay - result.paid_leave_pay) > 0.004:
        _recompute_statutory_and_net(conn, result, emp, period_start)
    return result


def apply_fractional_paid_leave_adjustments(conn: Any, results: list[Any], period_start: str, period_end: str) -> list[Any]:
    return [apply_fractional_paid_leave_adjustment(conn, result, period_start, period_end) for result in results]


def compute_payroll_with_fractional_leave(conn: Any, period_start: str, period_end: str) -> list[Any]:
    from core.payroll_engine import compute_payroll

    return apply_fractional_paid_leave_adjustments(conn, compute_payroll(conn, period_start, period_end), period_start, period_end)
