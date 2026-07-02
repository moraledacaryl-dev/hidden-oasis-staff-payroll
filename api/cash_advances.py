
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.cash_advance_service import (

    CashAdvancePayload,

    ensure_schema,

    normalize_method,

    now_iso,

    recalculate_balance,

    repayment_history,

    require_cash_advance_creator,

    require_cash_advance_editor,

    require_cash_advance_viewer,

)

from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

def _columns(conn, table: str) -> set[str]:

    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def _sync_legacy_fields(

    conn,

    advance_id: int,

    amount: float,

    deduction: float,

    balance: float,

    advance_date: str | None = None,

) -> None:

    columns = _columns(conn, "cash_advances")

    assignments: list[str] = []

    values: list[Any] = []

    if advance_date:

        for column in ("advance_date", "request_date"):

            if column in columns:

                assignments.append(f"{column}=?")

                values.append(advance_date)

    for column, value in (

        ("amount", amount),

        ("deduction_per_payroll", deduction),

        ("repayment_per_cutoff", deduction),

        ("remaining_balance", balance),

        ("outstanding_balance", balance),

        ("ledger_opening_balance", balance),

    ):

        if column in columns:

            assignments.append(f"{column}=?")

            values.append(round(float(value or 0), 2))

    if assignments:

        values.append(advance_id)

        conn.execute(f"UPDATE cash_advances SET {', '.join(assignments)} WHERE id=?", values)

def _insert_cash_advance(

    conn,

    *,

    payload: CashAdvancePayload,

    amount: float,

    deduction: float,

    method: str,

    display_name: str | None,

    stamp: str,

) -> int:

    columns = _columns(conn, "cash_advances")

    advance_date = payload.advance_date

    values_by_column: dict[str, Any] = {

        "employee_id": payload.employee_id,

        "advance_date": advance_date,

        "request_date": advance_date,

        "amount": amount,

        "reason": payload.reason,

        "approved_by": payload.approved_by,

        "repayment_method": method,

        "deduction_per_payroll": deduction,

        "repayment_per_cutoff": deduction,

        "remaining_balance": amount,

        "outstanding_balance": amount,

        "ledger_opening_balance": amount,

        "status": "Active",

        "notes": payload.notes,

        "created_by": display_name,

        "created_at": stamp,

        "updated_by": display_name,

        "updated_at": stamp,

    }

    insert_columns = [column for column in values_by_column if column in columns]

    placeholders = ",".join("?" for _ in insert_columns)

    column_list = ",".join(insert_columns)

    cur = conn.execute(

        f"INSERT INTO cash_advances({column_list}) VALUES({placeholders})",

        [values_by_column[column] for column in insert_columns],

    )

    return int(cur.lastrowid)

@router.get("/cash-advances")

def list_cash_advances(

    authorization: str | None = Header(default=None, alias="Authorization"),

    x_api_key: str | None = Header(default=None, alias="X-API-Key"),

) -> dict[str, Any]:

    require_cash_advance_viewer(authorization, x_api_key)

    conn = get_conn(DB_PATH)

    try:

        ensure_schema(conn)

        columns = _columns(conn, "cash_advances")

        date_expr = "COALESCE(ca.advance_date, ca.request_date)" if "request_date" in columns else "ca.advance_date"

        items = fetchall(

            conn,

            f"SELECT ca.*,e.full_name,e.employee_code,e.department,e.position "

            f"FROM cash_advances ca "

            f"LEFT JOIN employees e ON e.id=ca.employee_id "

            f"ORDER BY date({date_expr}) DESC,ca.id DESC",

        )

        for item in items:

            summary = recalculate_balance(conn, int(item["id"]))

            item.update(

                {

                    "remaining_balance": summary["balance"],

                    "status": summary["status"],

                    "total_repaid": summary["paid"],

                }

            )

            item["repayments"] = repayment_history(conn, int(item["id"]))

        conn.commit()

        return {"ok": True, "items": items}

    finally:

        conn.close()

@router.post("/cash-advances")

def save_cash_advance(

    payload: CashAdvancePayload,

    authorization: str | None = Header(default=None, alias="Authorization"),

    x_api_key: str | None = Header(default=None, alias="X-API-Key"),

) -> dict[str, Any]:

    user = (

        require_cash_advance_editor(authorization, x_api_key)

        if payload.id

        else require_cash_advance_creator(authorization, x_api_key)

    )

    amount = round(float(payload.amount or 0), 2)

    deduction = round(float(payload.deduction_per_payroll or 0), 2)

    if amount <= 0:

        raise HTTPException(status_code=422, detail="Cash advance amount must be greater than zero.")

    if deduction < 0:

        raise HTTPException(status_code=422, detail="Deduction per payroll cannot be negative.")

    if not str(payload.advance_date or "").strip():

        raise HTTPException(status_code=422, detail="Cash advance date is required.")

    method = normalize_method(payload.repayment_method)

    conn = get_conn(DB_PATH)

    try:

        ensure_schema(conn)

        stamp = now_iso()

        display_name = user.get("display_name")

        if payload.id:

            old = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (payload.id,))

            if not old:

                raise HTTPException(status_code=404, detail="Cash advance not found.")

            previous_amount = round(float(old.get("amount") or 0), 2)

            previous_opening = round(

                float(

                    old.get("ledger_opening_balance")

                    if old.get("ledger_opening_balance") is not None

                    else old.get("remaining_balance") or previous_amount

                ),

                2,

            )

            paid_to_date = round(max(0.0, previous_amount - previous_opening), 2)

            new_opening = round(max(0.0, amount - paid_to_date), 2)

            conn.execute(

                "UPDATE cash_advances SET employee_id=?,advance_date=?,reason=?,approved_by=?,repayment_method=?,status=?,notes=?,updated_by=?,updated_at=? WHERE id=?",

                (

                    payload.employee_id,

                    payload.advance_date,

                    payload.reason,

                    payload.approved_by,

                    method,

                    payload.status,

                    payload.notes,

                    display_name,

                    stamp,

                    payload.id,

                ),

            )

            advance_id = int(payload.id)

            _sync_legacy_fields(conn, advance_id, amount, deduction, new_opening, payload.advance_date)

        else:

            if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):

                raise HTTPException(status_code=404, detail="Employee not found.")

            advance_id = _insert_cash_advance(

                conn,

                payload=payload,

                amount=amount,

                deduction=deduction,

                method=method,

                display_name=display_name,

                stamp=stamp,

            )

            _sync_legacy_fields(conn, advance_id, amount, deduction, amount, payload.advance_date)

        summary = recalculate_balance(conn, advance_id)

        _sync_legacy_fields(conn, advance_id, amount, deduction, summary["balance"], payload.advance_date)

        conn.commit()

        item = fetchone(

            conn,

            "SELECT ca.*,e.full_name,e.employee_code,e.department,e.position "

            "FROM cash_advances ca "

            "LEFT JOIN employees e ON e.id=ca.employee_id "

            "WHERE ca.id=?",

            (advance_id,),

        ) or {}

        item.update(

            {

                "remaining_balance": summary["balance"],

                "status": summary["status"],

                "total_repaid": summary["paid"],

                "repayments": repayment_history(conn, advance_id),

            }

        )

        return {"ok": True, "item": item}

    except HTTPException:

        conn.rollback()

        raise

    finally:

        conn.close()

