from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

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
from core.money import money

router = APIRouter(prefix="/api/v1")


class LifecyclePayload(BaseModel):
    reason: str | None = None


def _columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _employee_department_sql(conn) -> tuple[str, str]:
    employee_columns = _columns(conn, "employees") if _table_exists(conn, "employees") else set()
    if "department" in employee_columns:
        return "e.department", ""
    if "department_id" in employee_columns and _table_exists(conn, "departments"):
        return "d.name", "LEFT JOIN departments d ON d.id=e.department_id"
    return "NULL", ""


def _cash_advance_select_sql(conn, where_clause: str = "") -> str:
    department_expr, department_join = _employee_department_sql(conn)
    return (
        "SELECT ca.*, e.full_name, e.employee_code, "
        f"{department_expr} AS department, e.position "
        "FROM cash_advances ca "
        "LEFT JOIN employees e ON e.id=ca.employee_id "
        f"{department_join} "
        f"{where_clause}"
    )


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
    ):
        if column in columns:
            assignments.append(f"{column}=?")
            values.append(money(value))

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
        "status": "Pending",
        "notes": payload.notes,
        "created_by": display_name,
        "created_at": stamp,
        "updated_by": display_name,
        "updated_at": stamp,
    }
    insert_columns = [column for column in values_by_column if column in columns]
    placeholders = ",".join("?" for _ in insert_columns)
    column_list = ",".join(insert_columns)
    cursor = conn.execute(
        f"INSERT INTO cash_advances({column_list}) VALUES({placeholders})",
        [values_by_column[column] for column in insert_columns],
    )
    return int(cursor.lastrowid)


def _ensure_lifecycle_events(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cash_advance_lifecycle_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cash_advance_id INTEGER NOT NULL,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            reason TEXT,
            actor_id INTEGER,
            actor_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ca_lifecycle_events_advance ON cash_advance_lifecycle_events(cash_advance_id,id)"
    )


def _canonical_status(value: str | None) -> str:
    status = str(value or "").strip()
    return "Active" if status in {"Approved", "Released"} else status


def _transition_cash_advance(
    conn,
    *,
    advance: dict[str, Any],
    target: str,
    allowed_from: set[str],
    user: dict[str, Any],
    reason: str | None = None,
    reason_required: bool = False,
) -> None:
    raw_status = str(advance.get("status") or "")
    current = _canonical_status(raw_status)
    if current not in allowed_from:
        raise HTTPException(status_code=409, detail=f"Cannot transition cash advance from {raw_status or 'Unknown'} to {target}.")

    clean_reason = str(reason or "").strip()
    if reason_required and not clean_reason:
        raise HTTPException(status_code=422, detail=f"A reason is required to mark this cash advance {target}.")

    actor_name = str(user.get("display_name") or "System")
    actor_id = user.get("id")
    stamp = now_iso()
    _ensure_lifecycle_events(conn)
    conn.execute(
        "UPDATE cash_advances SET status=?,updated_by=?,updated_at=? WHERE id=?",
        (target, actor_name, stamp, advance["id"]),
    )
    conn.execute(
        """
        INSERT INTO cash_advance_lifecycle_events(
            cash_advance_id,from_status,to_status,reason,actor_id,actor_name,created_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (advance["id"], raw_status, target, clean_reason or None, actor_id, actor_name, stamp),
    )


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
        items = fetchall(conn, _cash_advance_select_sql(conn, f"ORDER BY date({date_expr}) DESC, ca.id DESC"))
        for item in items:
            summary = recalculate_balance(conn, int(item["id"]))
            item.update({"remaining_balance": summary["balance"], "status": summary["status"], "total_repaid": summary["paid"]})
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
    user = require_cash_advance_editor(authorization, x_api_key) if payload.id else require_cash_advance_creator(authorization, x_api_key)
    amount = money(payload.amount)
    deduction = money(payload.deduction_per_payroll)
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

            advance_id = int(payload.id)
            stored_amount = money(old.get("amount") or 0)
            stored_basis = money(old.get("ledger_opening_balance") if old.get("ledger_opening_balance") is not None else stored_amount)
            if abs(amount - stored_basis) >= 0.005:
                raise HTTPException(status_code=409, detail="Original amount / balance basis cannot be changed in normal edit. Use owner correction instead.")

            # Lifecycle status is deliberately immutable through ordinary detail edits.
            # Approval/rejection/cancellation must use explicit transition endpoints.
            conn.execute(
                "UPDATE cash_advances SET employee_id=?,advance_date=?,reason=?,approved_by=?,repayment_method=?,notes=?,updated_by=?,updated_at=? WHERE id=?",
                (
                    payload.employee_id,
                    payload.advance_date,
                    payload.reason,
                    payload.approved_by,
                    method,
                    payload.notes,
                    display_name,
                    stamp,
                    payload.id,
                ),
            )
            _sync_legacy_fields(conn, advance_id, stored_amount, deduction, stored_basis, payload.advance_date)
        else:
            if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
                raise HTTPException(status_code=404, detail="Employee not found.")
            advance_id = _insert_cash_advance(conn, payload=payload, amount=amount, deduction=deduction, method=method, display_name=display_name, stamp=stamp)
            _sync_legacy_fields(conn, advance_id, amount, deduction, amount, payload.advance_date)

        summary = recalculate_balance(conn, advance_id)
        saved = fetchone(conn, "SELECT amount, ledger_opening_balance FROM cash_advances WHERE id=?", (advance_id,)) or {}
        saved_amount = money(saved.get("amount") or amount or 0)
        saved_basis = money(saved.get("ledger_opening_balance") if saved.get("ledger_opening_balance") is not None else saved_amount)
        _sync_legacy_fields(conn, advance_id, saved_amount, deduction, summary["balance"] if payload.id else saved_basis, payload.advance_date)
        conn.commit()

        item = fetchone(conn, _cash_advance_select_sql(conn, "WHERE ca.id=?"), (advance_id,)) or {}
        item.update({
            "remaining_balance": summary["balance"],
            "status": summary["status"],
            "total_repaid": summary["paid"],
            "repayments": repayment_history(conn, advance_id),
        })
        return {"ok": True, "item": item}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _load_for_transition(conn, cash_advance_id: int) -> dict[str, Any]:
    advance = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
    if not advance:
        raise HTTPException(status_code=404, detail="Cash advance not found.")
    return advance


def _transition_response(conn, cash_advance_id: int) -> dict[str, Any]:
    summary = recalculate_balance(conn, cash_advance_id)
    item = fetchone(conn, _cash_advance_select_sql(conn, "WHERE ca.id=?"), (cash_advance_id,)) or {}
    item.update({
        "remaining_balance": summary["balance"],
        "status": summary["status"],
        "total_repaid": summary["paid"],
        "repayments": repayment_history(conn, cash_advance_id),
    })
    return {"ok": True, "item": item}


@router.post("/cash-advances/{cash_advance_id}/approve")
def approve_cash_advance(
    cash_advance_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_cash_advance_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        advance = _load_for_transition(conn, cash_advance_id)
        _transition_cash_advance(conn, advance=advance, target="Active", allowed_from={"Pending", "Rejected"}, user=user)
        display_name = str(user.get("display_name") or "System")
        stamp = now_iso()
        conn.execute(
            """
            UPDATE cash_advances
               SET approved_by=COALESCE(NULLIF(approved_by,''), ?),
                   approved_by_user_id=?, approved_by_name=?, approved_at=?
             WHERE id=?
            """,
            (display_name, user.get("id"), display_name, stamp, cash_advance_id),
        )
        response = _transition_response(conn, cash_advance_id)
        conn.commit()
        return response
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/cash-advances/{cash_advance_id}/reject")
def reject_cash_advance(
    cash_advance_id: int,
    payload: LifecyclePayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_cash_advance_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        advance = _load_for_transition(conn, cash_advance_id)
        _transition_cash_advance(conn, advance=advance, target="Rejected", allowed_from={"Pending"}, user=user, reason=payload.reason, reason_required=True)
        response = _transition_response(conn, cash_advance_id)
        conn.commit()
        return response
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/cash-advances/{cash_advance_id}/cancel")
def cancel_cash_advance(
    cash_advance_id: int,
    payload: LifecyclePayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_cash_advance_editor(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        advance = _load_for_transition(conn, cash_advance_id)
        summary = recalculate_balance(conn, cash_advance_id)
        if float(summary.get("paid") or 0) > 0:
            raise HTTPException(status_code=409, detail="A cash advance with repayments cannot be cancelled. Reverse the repayments first.")
        _transition_cash_advance(conn, advance=advance, target="Cancelled", allowed_from={"Pending", "Rejected", "Active"}, user=user, reason=payload.reason, reason_required=True)
        response = _transition_response(conn, cash_advance_id)
        conn.commit()
        return response
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
