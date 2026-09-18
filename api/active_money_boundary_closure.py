from __future__ import annotations

from typing import Any

from core.db import fetchall, fetchone, get_setting
from core.money import money


def _install_fractional_leave_money_policy() -> None:
    import core.payroll_fractional_leave as module

    if getattr(module, "_active_money_boundary_closure", False):
        return

    original_apply = module.apply_fractional_paid_leave_adjustment
    original_recompute = module._recompute_statutory_and_net

    def recompute_statutory_and_net(
        conn: Any,
        result: Any,
        emp: dict[str, Any],
        period_start: str,
        period_end: str,
    ) -> None:
        # Money-boundary closure must not fork statutory policy. Delegate to
        # the canonical calendar-month recomputation installed by the core
        # fractional-leave module.
        original_recompute(conn, result, emp, period_start, period_end)

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
            recompute_statutory_and_net(conn, result, emp, period_start, period_end)
        return result

    module._recompute_statutory_and_net = recompute_statutory_and_net
    module.apply_fractional_paid_leave_adjustment = apply_fractional_paid_leave_adjustment
    module._active_money_boundary_closure = True


def _install_adjustment_snapshot_money_policy() -> None:
    import api.payroll_adjustments_aggregate as aggregate

    current = aggregate.current_adjustment
    if getattr(current, "_active_money_boundary_closure", False):
        return

    def current_adjustment(
        conn: Any,
        run_id: int,
        employee_id: int,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        adjustment = fetchone(
            conn,
            "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=? AND employee_id=?",
            (run_id, employee_id),
        )
        if adjustment:
            normalized = dict(adjustment)
            normalized["version"] = int(normalized.get("version") or 1)
            for field in ("additional_earning", "other_deduction", "cash_advance_amount"):
                normalized[field] = money(normalized.get(field) or 0)
            return normalized

        current_cash = money(item.get("cash_advance_deduction") or 0)
        advance_id: int | None = None
        if current_cash > 0:
            candidates = fetchall(
                conn,
                """
                SELECT id
                FROM cash_advances
                WHERE employee_id=?
                  AND status<>'Cancelled'
                  AND date(COALESCE(advance_date, request_date)) <= date(
                      COALESCE((SELECT period_end FROM payroll_runs WHERE id=?), date('now'))
                  )
                ORDER BY date(COALESCE(advance_date, request_date)), id
                """,
                (employee_id, run_id),
            )
            if len(candidates) == 1:
                advance_id = int(candidates[0]["id"])

        return {
            "additional_earning": 0.0,
            "additional_earning_note": None,
            "other_deduction": 0.0,
            "other_deduction_note": None,
            "cash_advance_id": advance_id,
            "cash_advance_amount": current_cash,
            "cash_advance_note": None,
            "version": 0,
        }

    current_adjustment._active_money_boundary_closure = True  # type: ignore[attr-defined]
    aggregate.current_adjustment = current_adjustment


def install_active_money_boundary_closure() -> None:
    _install_fractional_leave_money_policy()
    _install_adjustment_snapshot_money_policy()
