from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.cash_advance_service import calculate_balance, confirmed_new_repayments, recalculate_balance
from api.payroll_advance_allocations import (
    ALLOCATION_MODES, allocation_total, encode_allocations,
    plan_description, read_allocations,
)
from api.payroll_adjustment_events import append_adjustment_event
from api.payroll_adjustments import (
    AdjustmentPayload,
    _clean_note,
    _deactivate_legacy_draft_repayments,
    _event_reason,
    current_adjustment,
    ensure_schema,
    stamp,
    to_centavos,
)
from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.money import money

router = APIRouter(prefix="/api/v1")


def _eligible_advances(
    conn: Any,
    *,
    employee_id: int,
    period_end: str,
    persist_balances: bool = False,
) -> list[dict[str, Any]]:
    rows = fetchall(
        conn,
        """
        SELECT *
        FROM cash_advances
        WHERE employee_id=?
          AND COALESCE(status,'') NOT IN ('Cancelled','Rejected','Void','Voided')
          AND lower(COALESCE(repayment_method,'Payroll deduction')) LIKE '%payroll%'
          AND date(COALESCE(advance_date, request_date)) <= date(?)
          AND (NULLIF(TRIM(COALESCE(released_at,'')), '') IS NULL OR date(released_at) <= date(?))
        ORDER BY date(COALESCE(advance_date, request_date)), id
        """,
        (employee_id, period_end, period_end),
    )
    result: list[dict[str, Any]] = []
    # A stored Fully Paid status can be stale after older draft-payroll code
    # created a repayment prematurely. Let the authoritative repayment ledger,
    # not the cached status, determine whether a real balance remains.
    for row in rows:
        calculator = recalculate_balance if persist_balances else calculate_balance
        balance = money(calculator(conn, int(row["id"])).get("balance") or 0)
        if balance <= 0:
            continue
        result.append({**row, "live_balance": balance})
    return result


def _reserved_by_advance(
    conn: Any,
    *,
    employee_id: int,
    run_id: int,
    advances: list[dict[str, Any]],
) -> dict[int, float]:
    """Reserve older draft plans against the *actual* advance they target.

    Automatic plans allocate FIFO, while specific-advance plans reserve their
    chosen advances. Neither is an actual repayment.
    """
    current_run = fetchone(
        conn, "SELECT payout_date, period_end FROM payroll_runs WHERE id=?", (run_id,)
    ) or {}
    payment_date = str(current_run.get("payout_date") or current_run.get("period_end") or "")[:10]
    run_columns = {str(c[1]) for c in conn.execute("PRAGMA table_info(payroll_runs)")}
    supersession_filter = (
        "AND COALESCE(pr.superseded_by_run_id,0)=0"
        if "superseded_by_run_id" in run_columns else ""
    )
    earlier = fetchall(
        conn,
        f"""
        SELECT pia.*,pr.payout_date,pr.period_end
        FROM payroll_item_adjustments pia
        JOIN payroll_runs pr ON pr.id=pia.payroll_run_id
        WHERE pia.employee_id=? AND pia.payroll_run_id<>?
          AND COALESCE(pia.cash_advance_amount,0)>0
          AND COALESCE(pr.status,'')='Draft'
          AND (
            date(COALESCE(NULLIF(pr.payout_date,''),pr.period_end)) < date(?)
            OR (
              date(COALESCE(NULLIF(pr.payout_date,''),pr.period_end)) = date(?)
              AND pr.id < ?
            )
          )
          {supersession_filter}
        ORDER BY date(COALESCE(NULLIF(pr.payout_date,''),pr.period_end)),pr.id
        """,
        (employee_id, run_id, payment_date, payment_date, run_id),
    )
    balance = {
        int(row["id"]): money(row.get("live_balance") or 0)
        for row in advances
    }
    reserved = {key: 0.0 for key in balance}
    ids_fifo = [int(row["id"]) for row in advances]
    for row in earlier:
        deduction = money(row.get("cash_advance_amount") or 0)
        if str(row.get("cash_advance_allocation_mode") or "automatic") == "manual":
            plan = read_allocations(row)
            if allocation_total(plan) != deduction:
                raise ValueError("An earlier draft has an inconsistent advance allocation plan; correct it before editing another draft.")
        else:
            remaining = deduction
            plan = []
            for advance_id in ids_fifo:
                available = money(max(0, balance[advance_id] - reserved[advance_id]))
                used = money(min(remaining, available))
                if used > 0:
                    plan.append({"cash_advance_id": advance_id, "amount": used})
                    remaining = money(remaining - used)
                if remaining <= 0:
                    break
        for allocation in plan:
            advance_id = int(allocation["cash_advance_id"])
            if advance_id not in balance:
                continue
            available = money(max(0, balance[advance_id] - reserved[advance_id]))
            reserved[advance_id] = money(reserved[advance_id] + min(
                money(allocation["amount"]), available
            ))
    return reserved


def _other_draft_reserved_total(
    conn: Any, *, employee_id: int, run_id: int,
    advances: list[dict[str, Any]] | None = None,
) -> float:
    """Total actual draft reservation, including targeted plans."""
    if advances is None:
        return 0.0
    return money(sum(_reserved_by_advance(
        conn, employee_id=employee_id, run_id=run_id, advances=advances,
    ).values()))



def _suggested_total(advances: list[dict[str, Any]]) -> float:
    total = 0.0
    for advance in advances:
        available = money(max(0.0, float(advance.get("available_balance") or 0)))
        scheduled = money(
            max(
                0.0,
                float(
                    advance.get("custom_next_deduction")
                    or advance.get("deduction_per_payroll")
                    or advance.get("repayment_per_cutoff")
                    or 0
                ),
            )
        )
        total = money(total + min(available, scheduled))
    return money(total)


def _allocation_preview(
    advances: list[dict[str, Any]],
    amount: float,
) -> list[dict[str, Any]]:
    remaining = money(max(0.0, amount))
    allocations: list[dict[str, Any]] = []
    for advance in advances:
        if remaining <= 0:
            break
        available = money(max(0.0, float(advance.get("available_balance") or 0)))
        if available <= 0:
            continue
        applied = money(min(remaining, available))
        allocations.append(
            {
                "cash_advance_id": int(advance["id"]),
                "advance_date": advance.get("advance_date") or advance.get("request_date"),
                "reason": advance.get("reason"),
                "available_balance": available,
                "amount": applied,
            }
        )
        remaining = money(max(0.0, remaining - applied))
    return allocations


def _payroll_deduction_date(conn: Any, run_id: int, period_end: str) -> str:
    """Advances actually issued by payday can be deducted from that paycheck."""
    row = fetchone(
        conn, "SELECT payout_date FROM payroll_runs WHERE id=?", (run_id,)
    ) or {}
    payout = str(row.get("payout_date") or "")[:10]
    # Invalid/earlier payout dates must never truncate the original cutoff.
    from datetime import date
    try:
        end = date.fromisoformat(str(period_end)[:10])
        payday = date.fromisoformat(payout)
        return max(end, payday).isoformat()
    except (ValueError, TypeError):
        return str(period_end)[:10]


def _cash_availability_notes(
    conn: Any,
    *,
    employee_id: int,
    deduction_date: str,
    available_advances: list[dict[str, Any]],
    reserved_total: float,
) -> list[str]:
    """Explain a zero available balance without asserting any debt was repaid."""
    all_rows = fetchall(
        conn, "SELECT * FROM cash_advances WHERE employee_id=? ORDER BY id",
        (employee_id,),
    )
    balances_by_id = {
        int(row["id"]): money(row.get("available_balance") or 0)
        for row in available_advances
    }
    notes: list[str] = []
    for row in all_rows:
        prefix = f"Advance #{int(row['id'])}: "
        status = str(row.get("status") or "")
        if status in {"Cancelled", "Rejected", "Void", "Voided"}:
            notes.append(prefix + f"status is {status}; not eligible for deduction.")
            continue
        method = str(row.get("repayment_method") or "Payroll deduction").lower()
        if "payroll" not in method:
            notes.append(prefix + "repayment method is not Payroll deduction. Review the advance settings.")
            continue
        advance_date = str(row.get("advance_date") or row.get("request_date") or "")[:10]
        if advance_date > deduction_date:
            notes.append(prefix + f"dated {advance_date}, after payday eligibility {deduction_date}.")
            continue
        released_at = str(row.get("released_at") or "")[:10]
        if released_at and released_at > deduction_date:
            notes.append(prefix + f"recorded release {released_at} is after payday {deduction_date}.")
            continue
        summary = calculate_balance(conn, int(row["id"]))
        if money(summary.get("balance") or 0) <= 0:
            opening = row.get("ledger_opening_balance")
            if (
                opening is not None
                and money(opening) <= 0
                and money(row.get("amount") or 0) > 0
                and confirmed_new_repayments(conn, int(row["id"])) <= 0
            ):
                notes.append(prefix + "recorded opening balance is zero despite an advance amount. Check historical repayment records and owner correction before reopening any debt.")
            else:
                notes.append(prefix + "ledger shows no outstanding balance. Check recorded repayments before correcting it.")
            continue
        if balances_by_id.get(int(row["id"]), 0) <= 0 and reserved_total > 0:
            notes.append(prefix + "outstanding balance is reserved by an earlier or same-day active payroll draft.")
    if not all_rows:
        notes.append("No cash advance record exists for this employee.")
    return notes


def _cash_snapshot(
    conn: Any,
    *,
    run_id: int,
    employee_id: int,
    period_end: str,
    amount: float,
    persist_balances: bool = False,
) -> dict[str, Any]:
    deduction_date = _payroll_deduction_date(conn, run_id, period_end)
    advances = _eligible_advances(
        conn,
        employee_id=employee_id,
        period_end=deduction_date,
        persist_balances=persist_balances,
    )
    reserved_map = _reserved_by_advance(
        conn, employee_id=employee_id, run_id=run_id, advances=advances,
    )
    reserved_total = _other_draft_reserved_total(
        conn, employee_id=employee_id, run_id=run_id, advances=advances,
    )
    available_advances = [
        {
            **advance,
            "available_balance": money(max(
                0, money(advance.get("live_balance") or 0) - reserved_map.get(int(advance["id"]), 0),
            )),
        }
        for advance in advances
    ]
    total_available = money(
        sum(float(row.get("available_balance") or 0) for row in available_advances)
    )
    suggested = _suggested_total(available_advances)
    return {
        "cash_advances": available_advances,
        "cash_advance_total_available": total_available,
        "cash_advance_suggested": suggested,
        "cash_advance_allocations": _allocation_preview(available_advances, amount),
        "cash_advance_reserved_elsewhere": reserved_total,
        "cash_advance_deduction_date": deduction_date,
        "cash_advance_unconfirmed_issue": [
            int(advance["id"]) for advance in advances
            if int(advance.get("release_confirmation_required") or 0) == 1
            and not str(advance.get("released_at") or "").strip()
        ],
        "cash_advance_availability_notes": _cash_availability_notes(
            conn,
            employee_id=employee_id,
            deduction_date=deduction_date,
            available_advances=available_advances,
            reserved_total=reserved_total,
        ) if total_available <= 0 else [],
    }


@router.get("/payroll/runs/{run_id}/employees/{employee_id}/adjustments")
def get_adjustments(
    run_id: int,
    employee_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        item = fetchone(
            conn,
            "SELECT * FROM payroll_items WHERE payroll_run_id=? AND employee_id=?",
            (run_id, employee_id),
        )
        if not run or not item:
            raise HTTPException(status_code=404, detail="Payroll employee item not found.")

        adjustment = current_adjustment(conn, run_id, employee_id, item)
        cash = money(adjustment.get("cash_advance_amount") or 0)
        snapshot = _cash_snapshot(
            conn,
            run_id=run_id,
            employee_id=employee_id,
            period_end=str(run.get("period_end") or ""),
            amount=cash,
        )
        adjustment["legacy_cash_advance_id"] = adjustment.get("cash_advance_id")
        adjustment["cash_advance_id"] = None

        return {
            "ok": True,
            "run": run,
            "item": item,
            "adjustment": adjustment,
            **snapshot,
            "editable": run.get("status") == "Draft" and run.get("revision_treatment") != "adjust_paid",
        }
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/employees/{employee_id}/adjustments")
def save_adjustments(
    run_id: int,
    employee_id: int,
    payload: AdjustmentPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    earning = money(payload.additional_earning or 0)
    other = money(payload.other_deduction or 0)
    cash = money(payload.cash_advance_amount or 0)
    earning_note = _clean_note(payload.additional_earning_note)
    other_note = _clean_note(payload.other_deduction_note)
    cash_note = _clean_note(payload.cash_advance_note)

    if min(earning, other, cash) < 0:
        raise HTTPException(status_code=422, detail="Amounts cannot be negative.")
    if earning > 0 and not earning_note:
        raise HTTPException(status_code=422, detail="A reason is required for additional earnings.")
    if other > 0 and not other_note:
        raise HTTPException(status_code=422, detail="A reason is required for other deductions.")

    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        item = fetchone(
            conn,
            "SELECT * FROM payroll_items WHERE payroll_run_id=? AND employee_id=?",
            (run_id, employee_id),
        )
        if not run or not item:
            raise HTTPException(status_code=404, detail="Payroll employee item not found.")
        if run.get("status") != "Draft":
            raise HTTPException(status_code=409, detail="Open or create a Draft replacement before editing.")
        if run.get("revision_treatment") == "adjust_paid":
            raise HTTPException(status_code=409, detail="Paid revisions are difference-only.")

        existing = fetchone(
            conn,
            "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=? AND employee_id=?",
            (run_id, employee_id),
        )
        current_version = int(existing.get("version") or 1) if existing else 0
        if int(payload.expected_version or 0) != current_version:
            raise HTTPException(
                status_code=409,
                detail="This payroll adjustment changed after you opened it. Reload before saving.",
            )

        old = current_adjustment(conn, run_id, employee_id, item)
        old_earning = money(old.get("additional_earning") or 0)
        old_other = money(old.get("other_deduction") or 0)
        old_cash = money(old.get("cash_advance_amount") or 0)
        old_cash_id = int(old.get("cash_advance_id") or 0) or None

        snapshot = _cash_snapshot(
            conn,
            run_id=run_id,
            employee_id=employee_id,
            period_end=str(run.get("period_end") or ""),
            amount=cash,
            persist_balances=True,
        )
        total_available = money(snapshot["cash_advance_total_available"])
        suggested_cash = money(snapshot["cash_advance_suggested"])
        if cash > total_available:
            raise HTTPException(
                status_code=422,
                detail=f"Deduction cannot exceed the employee's available cash-advance balance of {total_available:.2f}.",
            )
        if cash > 0 and abs(cash - suggested_cash) >= 0.005 and not cash_note:
            raise HTTPException(
                status_code=422,
                detail="A reason is required when the cash advance deduction differs from the configured aggregate suggestion.",
            )

        current_cash = money(item.get("cash_advance_deduction") or 0)
        gross = money(money(item.get("gross_pay") or 0) - old_earning + earning)
        total_deductions = money(
            money(item.get("total_deductions") or 0) - old_other - current_cash + other + cash
        )
        net = money(gross - total_deductions)
        if net < 0:
            raise HTTPException(status_code=422, detail="Values cannot reduce net pay below zero.")

        now = stamp()
        actor = str(user.get("display_name") or "Payroll")
        actor_id = int(user.get("id")) if user.get("id") is not None else None
        request_id = _clean_note(x_request_id) or f"payroll-adjustment-{run_id}-{employee_id}-{now}"
        new_version = current_version + 1

        conn.execute(
            """
            UPDATE payroll_items
            SET other_earnings=?, gross_pay=?, cash_advance_deduction=?,
                other_deductions=?, total_deductions=?, net_pay=?
            WHERE id=?
            """,
            (
                money(money(item.get("other_earnings") or 0) - old_earning + earning),
                gross,
                cash,
                money(money(item.get("other_deductions") or 0) - old_other + other),
                total_deductions,
                net,
                item["id"],
            ),
        )

        if existing:
            cursor = conn.execute(
                """
                UPDATE payroll_item_adjustments
                SET additional_earning=?, additional_earning_note=?,
                    other_deduction=?, other_deduction_note=?,
                    cash_advance_id=NULL, cash_advance_amount=?, cash_advance_note=?,
                    version=?, updated_by=?, updated_at=?
                WHERE payroll_run_id=? AND employee_id=? AND version=?
                """,
                (
                    earning,
                    earning_note or None,
                    other,
                    other_note or None,
                    cash,
                    cash_note or None,
                    new_version,
                    actor,
                    now,
                    run_id,
                    employee_id,
                    current_version,
                ),
            )
            if cursor.rowcount != 1:
                raise HTTPException(
                    status_code=409,
                    detail="This payroll adjustment changed while you were saving. Reload and try again.",
                )
        else:
            conn.execute(
                """
                INSERT INTO payroll_item_adjustments(
                    payroll_run_id,payroll_item_id,employee_id,additional_earning,
                    additional_earning_note,other_deduction,other_deduction_note,
                    cash_advance_id,cash_advance_amount,cash_advance_note,version,
                    created_by,created_at,updated_by,updated_at
                ) VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?)
                """,
                (
                    run_id,
                    item["id"],
                    employee_id,
                    earning,
                    earning_note or None,
                    other,
                    other_note or None,
                    cash,
                    cash_note or None,
                    new_version,
                    actor,
                    now,
                    actor,
                    now,
                ),
            )

        financial_events = [
            (
                "additional_earning",
                old_earning,
                earning,
                None,
                _event_reason(earning_note, "Additional earning removed"),
                old_earning != earning,
            ),
            (
                "other_deduction",
                old_other,
                other,
                None,
                _event_reason(other_note, "Other deduction removed"),
                old_other != other,
            ),
            (
                "cash_advance_deduction",
                old_cash,
                cash,
                None,
                _event_reason(
                    cash_note,
                    "Configured aggregate cash advance deduction"
                    if abs(cash - suggested_cash) < 0.005 and cash > 0
                    else "Cash advance deduction removed",
                ),
                old_cash != cash or old_cash_id is not None,
            ),
        ]
        for kind, old_value, new_value, cash_advance_id, reason, changed in financial_events:
            if not changed:
                continue
            append_adjustment_event(
                conn,
                payroll_run_id=run_id,
                payroll_item_id=int(item["id"]),
                employee_id=employee_id,
                adjustment_kind=kind,
                old_centavos=to_centavos(old_value),
                new_centavos=to_centavos(new_value),
                cash_advance_id=cash_advance_id,
                reason=reason,
                actor_id=actor_id,
                actor_name=actor,
                request_id=request_id,
                created_at=now,
            )

        affected = _deactivate_legacy_draft_repayments(conn, run_id, actor, now)
        for advance_id in affected:
            recalculate_balance(conn, advance_id)

        conn.commit()
        refreshed_snapshot = _cash_snapshot(
            conn,
            run_id=run_id,
            employee_id=employee_id,
            period_end=str(run.get("period_end") or ""),
            amount=cash,
            persist_balances=True,
        )
        return {
            "ok": True,
            "version": new_version,
            "item": fetchone(conn, "SELECT * FROM payroll_items WHERE id=?", (item["id"],)),
            "totals": totals(conn, run_id),
            **refreshed_snapshot,
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()