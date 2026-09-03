from __future__ import annotations

from typing import Any, Callable

from core.db import fetchall, get_setting
from core.money import money


def _install_fractional_leave_money_policy() -> None:
    import core.payroll_fractional_leave as module

    if getattr(module, "_active_money_boundary_closure", False):
        return

    original_apply = module.apply_fractional_paid_leave_adjustment

    def recompute_statutory_and_net(
        conn: Any,
        result: Any,
        emp: dict[str, Any],
        period_start: str,
    ) -> None:
        from core.payroll_engine import (
            compute_semi_monthly_withholding_tax,
            get_month_previous_contribs,
            get_sss_share,
            parse_date,
        )

        result.gross_pay = money(
            result.regular_pay
            + result.ot_pay
            + result.night_diff_pay
            + result.holiday_pay
            + result.paid_leave_pay
            + result.freelance_pay
            + result.other_earnings
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
            result.sss_ee = money(max(0.0, sss_month_ee - prev["sss"]))
            result.sss_er = money(max(0.0, sss_month_er - prev["sss_er"]))
            result.sss_ec = money(max(0.0, sss_month_ec - prev["sss_ec"]))

        if has_current_gross and int(emp.get("benefits_philhealth") or 0):
            ph_rate = float(get_setting(conn, "philhealth_rate", "0.05") or 0.05)
            ph_floor = float(get_setting(conn, "philhealth_floor", "10000") or 10000)
            ph_ceiling = float(get_setting(conn, "philhealth_ceiling", "100000") or 100000)
            ph_base = min(max(declared, ph_floor), ph_ceiling)
            ph_month_total = ph_base * ph_rate
            if parse_date(period_start).day <= 15:
                result.philhealth_ee = money(ph_month_total / 4.0)
                result.philhealth_er = money(ph_month_total / 4.0)
            else:
                result.philhealth_ee = money(max(0.0, (ph_month_total / 2.0) - prev["philhealth"]))
                result.philhealth_er = money(max(0.0, (ph_month_total / 2.0) - prev["philhealth_er"]))

        if has_current_gross and int(emp.get("benefits_pagibig") or 0):
            pi_rate = float(get_setting(conn, "pagibig_rate", "0.02") or 0.02)
            pi_er_rate = float(get_setting(conn, "pagibig_employer_rate", "0.02") or 0.02)
            pi_ceiling = float(get_setting(conn, "pagibig_ceiling", "10000") or 10000)
            pi_base = min(declared, pi_ceiling)
            pi_month_ee = pi_base * pi_rate
            pi_month_er = pi_base * pi_er_rate
            if parse_date(period_start).day <= 15:
                result.pagibig_ee = money(pi_month_ee / 2.0)
                result.pagibig_er = money(pi_month_er / 2.0)
            else:
                result.pagibig_ee = money(max(0.0, pi_month_ee - prev["pagibig"]))
                result.pagibig_er = money(max(0.0, pi_month_er - prev["pagibig_er"]))

        if has_current_gross and int(emp.get("benefits_tax") or 0):
            taxable_comp = result.gross_pay - result.sss_ee - result.philhealth_ee - result.pagibig_ee
            result.tax = compute_semi_monthly_withholding_tax(taxable_comp)

        statutory_and_manual = money(
            result.sss_ee
            + result.philhealth_ee
            + result.pagibig_ee
            + result.tax
            + result.other_deductions
        )
        ca_capacity = money(max(0.0, result.gross_pay - statutory_and_manual))
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
            ca_deduction = money(ca_deduction + amount)
        result.cash_advance_deduction = money(ca_deduction)
        result.total_deductions = money(statutory_and_manual + result.cash_advance_deduction)
        result.net_pay = money(result.gross_pay - result.total_deductions)

    def apply_fractional_paid_leave_adjustment(
        conn: Any,
        result: Any,
        period_start: str,
        period_end: str,
    ) -> Any:
        result = original_apply(conn, result, period_start, period_end)
        emp = module._active_employee(conn, int(result.employee_id))
        if not emp:
            return result
        corrected_days = module._correct_paid_leave_days(conn, int(result.employee_id), period_start, period_end)
        standard_paid_hours = float(get_setting(conn, "standard_daily_paid_hours", "8") or 8)
        hourly_rate = float(emp.get("hourly_rate") or 0)
        corrected_pay = money(corrected_days * standard_paid_hours * hourly_rate)
        if corrected_pay != money(result.paid_leave_pay):
            result.paid_leave_pay = corrected_pay
            recompute_statutory_and_net(conn, result, emp, period_start)
        return result

    module._recompute_statutory_and_net = recompute_statutory_and_net
    module.apply_fractional_paid_leave_adjustment = apply_fractional_paid_leave_adjustment
    module._active_money_boundary_closure = True


def _install_adjustment_snapshot_money_policy() -> None:
    import api.payroll_adjustments_aggregate as aggregate

    current: Callable[..., dict[str, Any]] = aggregate.current_adjustment
    if getattr(current, "_active_money_boundary_closure", False):
        return

    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current(*args, **kwargs)
        normalized = dict(result)
        for field in ("additional_earning", "other_deduction", "cash_advance_amount"):
            normalized[field] = money(normalized.get(field) or 0)
        return normalized

    wrapped._active_money_boundary_closure = True  # type: ignore[attr-defined]
    aggregate.current_adjustment = wrapped


def install_active_money_boundary_closure() -> None:
    _install_fractional_leave_money_policy()
    _install_adjustment_snapshot_money_policy()
