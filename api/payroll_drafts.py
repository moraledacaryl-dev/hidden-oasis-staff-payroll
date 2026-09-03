from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException

from api.payroll_service import (
    PayrollDraftRequest,
    approve_payroll_run as approve_payroll_run_v1,
    item_dict,
    list_payroll_runs as list_payroll_runs_v1,
    lock_payroll_run as lock_payroll_run_v1,
    must_be_payroll_user,
    now_iso,
    totals,
)
from core.corrections import mark_eligible_corrections_applied
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.money import money
from core.payroll_engine import update_payroll_status
from core.payroll_fractional_leave import apply_fractional_paid_leave_adjustment
from core.payroll_split_shift_policy import compute_payroll_per_shift
from core.quality import build_payroll_preflight_checks, summarize_checks

router = APIRouter(prefix="/api/v1")


def payroll_business_date() -> date:
    return datetime.now(ZoneInfo("Asia/Manila")).date()


def _validate_semimonthly_period(start: date, end: date) -> None:
    if start.year != end.year or start.month != end.month:
        raise HTTPException(status_code=422, detail="A semi-monthly payroll period must stay within one calendar month.")
    last_day = monthrange(start.year, start.month)[1]
    if not ((start.day == 1 and end.day == 15) or (start.day == 16 and end.day == last_day)):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Use either {start.year}-{start.month:02d}-01 to {start.year}-{start.month:02d}-15 "
                f"or {start.year}-{start.month:02d}-16 to {start.year}-{start.month:02d}-{last_day:02d}."
            ),
        )


def _active_overlap(conn: Any, start: str, end: str) -> dict[str, Any] | None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(payroll_runs)").fetchall()}
    where = "status NOT IN ('Cancelled','Voided')"
    if "superseded_by_run_id" in columns:
        where += " AND superseded_by_run_id IS NULL"
    return fetchone(
        conn,
        f"""
        SELECT id,period_start,period_end,run_label,status
        FROM payroll_runs
        WHERE {where}
          AND date(period_start)<=date(?)
          AND date(period_end)>=date(?)
        ORDER BY id
        LIMIT 1
        """,
        (end, start),
    )


def _apply_period_cash_advance_deduction(conn: Any, result: Any, period_start: str, period_end: str) -> Any:
    """Default cash-advance deduction is limited to advances dated inside this cutoff."""
    employee_id = int(result.employee_id)
    rows = fetchall(
        conn,
        """
        SELECT
            id,
            COALESCE(remaining_balance, outstanding_balance, amount, 0) AS balance,
            COALESCE(custom_next_deduction, deduction_per_payroll, repayment_per_cutoff, 0) AS scheduled_deduction
        FROM cash_advances
        WHERE employee_id=?
          AND COALESCE(remaining_balance, outstanding_balance, amount, 0) > 0
          AND COALESCE(status,'') NOT IN ('Cancelled','Fully Paid','Rejected','Void','Voided')
          AND lower(COALESCE(repayment_method,'Payroll deduction')) LIKE '%payroll%'
          AND date(COALESCE(advance_date, request_date)) <= date(?)
        ORDER BY date(COALESCE(advance_date, request_date)), id
        """,
        (employee_id, period_end),
    )
    statutory_and_manual = money(
        money(result.sss_ee or 0)
        + money(result.philhealth_ee or 0)
        + money(result.pagibig_ee or 0)
        + money(result.tax or 0)
        + money(result.other_deductions or 0)
    )
    gross = money(result.gross_pay or 0)
    capacity = money(max(0.0, gross - statutory_and_manual))
    deduction = 0.0
    for row in rows:
        scheduled = money(row.get("scheduled_deduction") or 0)
        balance = money(row.get("balance") or 0)
        if scheduled <= 0 or balance <= 0 or capacity <= deduction:
            continue
        deduction = money(deduction + min(balance, scheduled, capacity - deduction))
    result.cash_advance_deduction = money(deduction)
    result.total_deductions = money(statutory_and_manual + result.cash_advance_deduction)
    result.net_pay = money(gross - result.total_deductions)
    return result


@router.get("/payroll/runs")
def list_payroll_runs(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    return list_payroll_runs_v1(authorization, x_api_key)


@router.post("/payroll/runs/draft")
def create_payroll_draft(
    payload: PayrollDraftRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    start_date = payload.period_start
    end_date = payload.period_end

    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date cannot be before start date.")
    if end_date >= payroll_business_date():
        raise HTTPException(status_code=409, detail="Payroll can only be created after the payroll period has fully ended.")
    if payload.payout_date < end_date:
        raise HTTPException(status_code=422, detail="Payout date cannot be before the payroll period ends.")

    label = payload.run_label.strip() or "Semi-monthly"
    if "semi-monthly" in label.lower():
        _validate_semimonthly_period(start_date, end_date)

    start = start_date.isoformat()
    end = end_date.isoformat()
    conn = get_conn(DB_PATH)
    try:
        overlap = _active_overlap(conn, start, end)
        if overlap:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Active payroll run #{overlap['id']} already covers "
                    f"{overlap['period_start']} to {overlap['period_end']}. "
                    "Edit that Draft or use the controlled revision action."
                ),
            )

        checks = build_payroll_preflight_checks(conn, start, end)
        blockers = [check for check in checks if check.get("severity") == "Blocker"]
        if blockers:
            raise HTTPException(status_code=409, detail={"message": "Draft blocked by payroll QA blockers.", "checks": checks})

        stamp = now_iso()
        cursor = conn.execute(
            """
            INSERT INTO payroll_runs(
                period_start,period_end,payout_date,run_label,status,
                prepared_by,validation_summary,created_at
            ) VALUES(?,?,?,?,'Draft',?,?,?)
            """,
            (start, end, payload.payout_date.isoformat(), label, user.get("display_name"), summarize_checks(checks), stamp),
        )
        run_id = int(cursor.lastrowid)
        columns = [
            "employee_id","regular_hours","regular_pay","approved_ot_hours","ot_pay",
            "night_diff_hours","night_diff_pay","holiday_pay","paid_leave_days","paid_leave_pay",
            "freelance_pay","other_earnings","gross_pay","late_minutes","undertime_minutes",
            "unpaid_absence_days","sss_ee","philhealth_ee","pagibig_ee","sss_er","sss_ec",
            "philhealth_er","pagibig_er","tax","cash_advance_deduction","other_deductions",
            "total_deductions","net_pay","warnings",
        ]
        for result in compute_payroll_per_shift(conn, start, end):
            result = apply_fractional_paid_leave_adjustment(conn, result, start, end)
            result = _apply_period_cash_advance_deduction(conn, result, start, end)
            data = item_dict(result)
            values = [run_id] + [data.get(column, 0) for column in columns] + [stamp]
            conn.execute(
                f"INSERT INTO payroll_items(payroll_run_id,{','.join(columns)},created_at) "
                f"VALUES({','.join('?' for _ in values)})",
                values,
            )

        mark_eligible_corrections_applied(conn, run_id, start)
        conn.commit()
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        run["totals"] = totals(conn, run_id)
        return {"ok": True, "run": run, "checks": checks, "mode": "draft_saved_not_released"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/approve")
def approve_payroll_run(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    return approve_payroll_run_v1(run_id, authorization, x_api_key)


@router.post("/payroll/runs/{run_id}/paid")
def mark_payroll_run_paid(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    user = must_be_payroll_user(authorization, x_api_key)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Only owner can mark payroll as paid.")
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        if run.get("status") != "Approved":
            raise HTTPException(status_code=409, detail="Only approved payroll runs can be marked paid.")
        try:
            update_payroll_status(conn, run_id, "Paid", str(user.get("display_name") or "Owner"))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        updated = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        updated["totals"] = totals(conn, run_id)
        return {"ok": True, "run": updated, "mode": "paid_cash_advances_applied"}
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/lock")
def lock_payroll_run(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    return lock_payroll_run_v1(run_id, authorization, x_api_key)
