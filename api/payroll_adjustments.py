from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.cash_advance_service import ensure_schema as ensure_cash_schema, recalculate_balance
from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class AdjustmentPayload(BaseModel):
    additional_earning: float = 0
    additional_earning_note: str | None = None
    other_deduction: float = 0
    other_deduction_note: str | None = None
    cash_advance_id: int | None = None
    cash_advance_amount: float = 0


def stamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def ensure_schema(conn) -> None:
    ensure_cash_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_item_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL,
            payroll_item_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            additional_earning REAL NOT NULL DEFAULT 0,
            additional_earning_note TEXT,
            other_deduction REAL NOT NULL DEFAULT 0,
            other_deduction_note TEXT,
            cash_advance_id INTEGER,
            cash_advance_amount REAL NOT NULL DEFAULT 0,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(payroll_run_id, employee_id)
        )
        """
    )
    conn.commit()


def reserved(conn, advance_id: int, run_id: int) -> float:
    """Return planned deductions held by other active draft payroll runs.

    Draft reservations live in payroll_item_adjustments only. They are not cash
    advance repayments and must never reduce the official balance before payment.
    """
    row = fetchone(
        conn,
        """
        SELECT COALESCE(SUM(pia.cash_advance_amount), 0) AS total
        FROM payroll_item_adjustments pia
        JOIN payroll_runs pr ON pr.id = pia.payroll_run_id
        WHERE pia.cash_advance_id=?
          AND pia.payroll_run_id<>?
          AND COALESCE(pia.cash_advance_amount, 0)>0
          AND COALESCE(pr.status, '')='Draft'
          AND COALESCE(pr.superseded_by_run_id, 0)=0
        """,
        (advance_id, run_id),
    ) or {}
    return round(float(row.get("total") or 0), 2)


def current_adjustment(conn, run_id: int, employee_id: int, item: dict[str, Any]) -> dict[str, Any]:
    adjustment = fetchone(
        conn,
        "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=? AND employee_id=?",
        (run_id, employee_id),
    )
    if adjustment:
        return adjustment

    current_cash = round(float(item.get("cash_advance_deduction") or 0), 2)
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
        "additional_earning": 0,
        "additional_earning_note": None,
        "other_deduction": 0,
        "other_deduction_note": None,
        "cash_advance_id": advance_id,
        "cash_advance_amount": current_cash,
    }


def _deactivate_legacy_draft_repayments(conn, run_id: int, actor: str, now: str) -> set[int]:
    """Neutralize repayments incorrectly created by older draft-adjustment code."""
    rows = fetchall(
        conn,
        """
        SELECT id, cash_advance_id
        FROM cash_advance_repayments
        WHERE payroll_run_id=?
          AND COALESCE(active,1)=1
          AND COALESCE(source,'')='Payroll'
        """,
        (run_id,),
    )
    affected: set[int] = set()
    for row in rows:
        affected.add(int(row["cash_advance_id"]))
        conn.execute(
            """
            UPDATE cash_advance_repayments
            SET active=0,
                reversed_by=?,
                reversed_at=?,
                reversal_reason='Draft deduction converted to non-posting plan',
                updated_by=?,
                updated_at=?
            WHERE id=?
            """,
            (actor, now, actor, now, row["id"]),
        )
    return affected


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
        selected_id = int(adjustment.get("cash_advance_id") or 0)
        options = []
        for advance in fetchall(
            conn,
            """
            SELECT *
            FROM cash_advances
            WHERE employee_id=?
              AND status<>'Cancelled'
              AND date(COALESCE(advance_date, request_date)) <= date(?)
            ORDER BY date(COALESCE(advance_date, request_date)), id
            """,
            (employee_id, run.get("period_end")),
        ):
            selected = selected_id == int(advance["id"])
            available = recalculate_balance(conn, int(advance["id"]))["balance"] - reserved(
                conn, int(advance["id"]), run_id
            )
            if available > 0 or selected:
                options.append({**advance, "available_balance": round(max(0, available), 2)})

        return {
            "ok": True,
            "run": run,
            "item": item,
            "adjustment": adjustment,
            "cash_advances": options,
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
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    earning = round(float(payload.additional_earning or 0), 2)
    other = round(float(payload.other_deduction or 0), 2)
    cash = round(float(payload.cash_advance_amount or 0), 2)
    if min(earning, other, cash) < 0:
        raise HTTPException(status_code=422, detail="Amounts cannot be negative.")
    if cash > 0 and not payload.cash_advance_id:
        raise HTTPException(status_code=422, detail="Select a cash advance.")

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

        old = current_adjustment(conn, run_id, employee_id, item)
        old_earning = round(float(old.get("additional_earning") or 0), 2)
        old_other = round(float(old.get("other_deduction") or 0), 2)

        if payload.cash_advance_id:
            advance = fetchone(
                conn,
                "SELECT * FROM cash_advances WHERE id=? AND employee_id=?",
                (payload.cash_advance_id, employee_id),
            )
            if not advance:
                raise HTTPException(status_code=404, detail="Cash advance not found for this employee.")
            advance_date = str(advance.get("advance_date") or advance.get("request_date") or "")[:10]
            period_end = str(run.get("period_end") or "")[:10]
            if advance_date and period_end and advance_date > period_end:
                raise HTTPException(
                    status_code=422,
                    detail="This cash advance is dated after the payroll period and cannot be applied to this run.",
                )
            available = recalculate_balance(conn, int(payload.cash_advance_id))["balance"] - reserved(
                conn, int(payload.cash_advance_id), run_id
            )
            if cash > round(available, 2):
                raise HTTPException(
                    status_code=422,
                    detail=f"Deduction cannot exceed the available balance of {available:.2f}.",
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

        now = stamp()
        actor = str(user.get("display_name") or "Payroll")
        conn.execute(
            """
            INSERT INTO payroll_item_adjustments(
                payroll_run_id,payroll_item_id,employee_id,additional_earning,
                additional_earning_note,other_deduction,other_deduction_note,
                cash_advance_id,cash_advance_amount,created_by,created_at,updated_by,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(payroll_run_id,employee_id) DO UPDATE SET
                additional_earning=excluded.additional_earning,
                additional_earning_note=excluded.additional_earning_note,
                other_deduction=excluded.other_deduction,
                other_deduction_note=excluded.other_deduction_note,
                cash_advance_id=excluded.cash_advance_id,
                cash_advance_amount=excluded.cash_advance_amount,
                updated_by=excluded.updated_by,
                updated_at=excluded.updated_at
            """,
            (
                run_id,
                item["id"],
                employee_id,
                earning,
                payload.additional_earning_note,
                other,
                payload.other_deduction_note,
                payload.cash_advance_id,
                cash,
                actor,
                now,
                actor,
                now,
            ),
        )

        affected = _deactivate_legacy_draft_repayments(conn, run_id, actor, now)
        for advance_id in affected:
            recalculate_balance(conn, advance_id)

        conn.commit()
        return {
            "ok": True,
            "item": fetchone(conn, "SELECT * FROM payroll_items WHERE id=?", (item["id"],)),
            "totals": totals(conn, run_id),
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
