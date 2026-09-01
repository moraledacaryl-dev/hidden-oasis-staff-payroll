from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.cash_advance_service import ensure_schema as ensure_cash_schema, recalculate_balance
from api.payroll_adjustment_events import append_adjustment_event, ensure_adjustment_event_schema
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

router = APIRouter(prefix="/api/v1")


def _eligible_advances(
    conn: Any,
    *,
    employee_id: int,
    period_end: str,
) -> list[dict[str, Any]]:
    rows = fetchall(
        conn,
        """
        SELECT *
        FROM cash_advances
        WHERE employee_id=?
          AND COALESCE(status,'') NOT IN ('Cancelled','Fully Paid','Rejected','Void','Voided')
          AND lower(COALESCE(repayment_method,'Payroll deduction')) LIKE '%payroll%'
          AND date(COALESCE(advance_date, request_date)) <= date(?)
        ORDER BY date(COALESCE(advance_date, request_date)), id
        """,
        (employee_id, period_end),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        balance = round(float(recalculate_balance(conn, int(row["id"])).get("balance") or 0), 2)
        if balance <= 0:
            continue
        result.append({**row, "live_balance": balance})
    return result


def _other_draft_reserved_total(conn: Any, *, employee_id: int, run_id: int) -> float:
    """Return aggregate cash-advance deductions reserved by other active drafts.

    New payroll edits are employee-level FIFO allocations. Older exact-advance
    draft rows still contribute to this aggregate reservation so mixed-version
    drafts cannot over-reserve the employee's total outstanding balance.
    """
    row = fetchone(
        conn,
        """
        SELECT COALESCE(SUM(pia.cash_advance_amount), 0) AS total
        FROM payroll_item_adjustments pia
        JOIN payroll_runs pr ON pr.id=pia.payroll_run_id
        WHERE pia.employee_id=?
          AND pia.payroll_run_id<>?
          AND COALESCE(pia.cash_advance_amount,0)>0
          AND COALESCE(pr.status,'')='Draft'
          AND COALESCE(pr.superseded_by_run_id,0)=0
        """,
        (employee_id, run_id),
    ) or {}
    return round(max(0.0, float(row.get("total") or 0)), 2)


def _available_after_other_drafts(
    advances: list[dict[str, Any]],
    reserved_total: float,
) -> list[dict[str, Any]]:
    """Apply existing aggregate reservations FIFO for a deterministic preview."""
    remaining_reserved = round(max(0.0, reserved_total), 2)
    result: list[dict[str, Any]] = []
    for advance in advances:
        balance = round(max(0.0, float(advance.get("live_balance") or 0)), 2)
        consumed = round(min(balance, remaining_reserved), 2)
        remaining_reserved = round(max(0.0, remaining_reserved - consumed), 2)
        available = round(max(0.0, balance - consumed), 2)
        result.append({**advance, "available_balance": available})
    return result


def _suggested_total(advances: list[dict[str, Any]]) -> float:
    total = 0.0
    for advance in advances:
        available = round(max(0.0, float(advance.get("available_balance") or 0)), 2)
        scheduled = round(
            max(
                0.0,
                float(
                    advance.get("custom_next_deduction")
                    or advance.get("deduction_per_payroll")
                    or advance.get("repayment_per_cutoff")
                    or 0
                ),
            ),
            2,
        )
        total += min(available, scheduled)
    return round(total, 2)


def _allocation_preview(
    advances: list[dict[str, Any]],
    amount: float,
) -> list[dict[str, Any]]:
    remaining = round(max(0.0, amount), 2)
    allocations: list[dict[str, Any]] = []
    for advance in advances:
        if remaining <= 0:
            break
        available = round(max(0.0, float(advance.get("available_balance") or 0)), 2)
        if available <= 0:
            continue
        applied = round(min(remaining, available), 2)
        allocations.append(
            {
                "cash_advance_id": int(advance["id"]),
                "advance_date": advance.get("advance_date") or advance.get("request_date"),
                "reason": advance.get("reason"),
                "available_balance": available,
                "amount": applied,
            }
        )
        remaining = round(max(0.0, remaining - applied), 2)
    return allocations


def _cash_snapshot(
    conn: Any,
    *,
    run_id: int,
    employee_id: int,
    period_end: str,
    amount: float,
) -> dict[str, Any]:
    advances = _eligible_advances(conn, employee_id=employee_id, period_end=period_end)
    reserved_total = _other_draft_reserved_total(conn, employee_id=employee_id, run_id=run_id)
    available_advances = _available_after_other_drafts(advances, reserved_total)
    total_available = round(
        sum(float(row.get("available_balance") or 0) for row in available_advances),
        2,
    )
    suggested = _suggested_total(available_advances)
    return {
        "cash_advances": available_advances,
        "cash_advance_total_available": total_available,
        "cash_advance_suggested": suggested,
        "cash_advance_allocations": _allocation_preview(available_advances, amount),
        "cash_advance_reserved_elsewhere": reserved_total,
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
        ensure_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        item = fetchone(
            conn,
            "SELECT * FROM payroll_items WHERE payroll_run_id=? AND employee_id=?",
            (run_id, employee_id),
        )
        if not run or not item:
            raise HTTPException(status_code=404, detail="Payroll employee item not found.")

        adjustment = current_adjustment(conn, run_id, employee_id, item)
        cash = round(float(adjustment.get("cash_advance_amount") or 0), 2)
        snapshot = _cash_snapshot(
            conn,
            run_id=run_id,
            employee_id=employee_id,
            period_end=str(run.get("period_end") or ""),
            amount=cash,
        )
        # New edits are employee-level FIFO plans. Preserve the legacy exact id
        # only as read-only provenance; the editor intentionally does not reuse it.
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
    earning = round(float(payload.additional_earning or 0), 2)
    other = round(float(payload.other_deduction or 0), 2)
    cash = round(float(payload.cash_advance_amount or 0), 2)
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
        old_earning = round(float(old.get("additional_earning") or 0), 2)
        old_other = round(float(old.get("other_deduction") or 0), 2)
        old_cash = round(float(old.get("cash_advance_amount") or 0), 2)
        old_cash_id = int(old.get("cash_advance_id") or 0) or None

        snapshot = _cash_snapshot(
            conn,
            run_id=run_id,
            employee_id=employee_id,
            period_end=str(run.get("period_end") or ""),
            amount=cash,
        )
        total_available = round(float(snapshot["cash_advance_total_available"]), 2)
        suggested_cash = round(float(snapshot["cash_advance_suggested"]), 2)
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

        current_cash = round(float(item.get("cash_advance_deduction") or 0), 2)
        gross = round(float(item.get("gross_pay") or 0) - old_earning + earning, 2)
        total_deductions = round(
            float(item.get("total_deductions") or 0) - old_other - current_cash + other + cash,
            2,
        )
        net = round(gross - total_deductions, 2)
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
                round(float(item.get("other_earnings") or 0) - old_earning + earning, 2),
                gross,
                cash,
                round(float(item.get("other_deductions") or 0) - old_other + other, 2),
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
