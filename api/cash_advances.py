from __future__ import annotations

from datetime import date
from typing import Any, Literal
from zoneinfo import ZoneInfo
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, field_validator

from api.cash_advance_service import (
    CashAdvancePayload,
    calculate_balance,
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
from core.drawer import create_drawer_cash_advance_movement
from core.integration_accounting import build_cash_advance_release_payload
from core.integration_outbox import enqueue_event, ensure_integration_schema

router = APIRouter(prefix="/api/v1")


class LifecyclePayload(BaseModel):
    reason: str | None = None


class ReleasePayload(BaseModel):
    # Separate physical disbursement from approval. Never infer cash movement.
    release_date: date
    release_method: Literal["Cash Drawer", "GCash", "Bank Transfer"]
    reference: str | None = None
    confirmed_received: bool = False

    @field_validator("reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        cleaned = (value or "").strip()
        if len(cleaned) > 160:
            raise ValueError("Release reference must be at most 160 characters.")
        return cleaned or None




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
        # Existing records stay out of this prospective-only release workflow.
        "release_confirmation_required": 1,
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
        columns = _columns(conn, "cash_advances")
        date_expr = "COALESCE(ca.advance_date, ca.request_date)" if "request_date" in columns else "ca.advance_date"
        items = fetchall(conn, _cash_advance_select_sql(conn, f"ORDER BY date({date_expr}) DESC, ca.id DESC"))
        for item in items:
            summary = calculate_balance(conn, int(item["id"]))
            item.update({"remaining_balance": summary["balance"], "status": summary["status"], "total_repaid": summary["paid"]})
            item["repayments"] = repayment_history(conn, int(item["id"]))
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
            # Never reassign an already issued financial movement to another
            # employee or date through an ordinary form edit.
            if str(old.get("released_at") or "").strip() and (
                int(payload.employee_id) != int(old["employee_id"])
                or str(payload.advance_date)[:10] != str(old.get("advance_date") or old.get("request_date") or "")[:10]
            ):
                raise HTTPException(status_code=409, detail="Issued advance identity and advance date are immutable. Use an audited correction.")

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


@router.post("/cash-advances/{cash_advance_id}/release")
def confirm_cash_advance_release(
    cash_advance_id: int,
    payload: ReleasePayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Confirm funds actually issued, then atomically queue Accounting review.

    Historical records are excluded. Delivery is not an Accounting posting.
    """
    user = require_cash_advance_editor(authorization, x_api_key)
    if not payload.confirmed_received:
        raise HTTPException(status_code=422, detail="Confirm that the funds were actually issued.")
    if payload.release_date > datetime.now(ZoneInfo("Asia/Manila")).date():
        raise HTTPException(status_code=422, detail="Release date cannot be in the future.")
    if payload.release_method != "Cash Drawer" and not payload.reference:
        raise HTTPException(status_code=422, detail="Enter the actual transfer reference.")
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        # Schema initialization commits: it must precede the money transaction.
        ensure_integration_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        advance = _load_for_transition(conn, cash_advance_id)
        if int(advance.get("release_confirmation_required") or 0) != 1:
            raise HTTPException(status_code=409, detail="Historical advances require a separate reconciliation process.")
        reference = payload.reference or f"CA-{cash_advance_id}"
        existing_date = str(advance.get("released_at") or "")[:10]
        if existing_date:
            identical = (
                existing_date == payload.release_date.isoformat()
                and advance.get("release_method") == payload.release_method
                and str(advance.get("release_reference") or "") == reference
            )
            if not identical:
                raise HTTPException(status_code=409, detail="Advance was released with different details. Use an audited correction.")
            conn.rollback()
            return {"ok": True, "already_recorded": True, "cash_advance_id": cash_advance_id}

        if _canonical_status(advance.get("status")) != "Active":
            raise HTTPException(status_code=409, detail="Approve the advance before confirming disbursement.")
        if not str(advance.get("approved_at") or "").strip():
            raise HTTPException(status_code=409, detail="An attributed approval is required before release.")
        if payload.release_date < date.fromisoformat(str(advance.get("advance_date") or advance.get("request_date"))[:10]):
            raise HTTPException(status_code=422, detail="Release date cannot precede the advance date.")
        paid = calculate_balance(conn, cash_advance_id)["paid"]
        if paid > 0:
            raise HTTPException(status_code=409, detail="Repayments already exist; reconcile this advance historically instead.")

        _transition_cash_advance(
            conn, advance=advance, target="Released", allowed_from={"Active"}, user=user,
            reason="Confirmed funds issued; method and reference recorded separately.",
        )
        conn.execute(
            """UPDATE cash_advances
               SET release_method=?, release_reference=?, released_at=?, released_by=?
               WHERE id=?""",
            (
                payload.release_method, reference, payload.release_date.isoformat(),
                str(user.get("display_name") or "System"), cash_advance_id,
            ),
        )
        if payload.release_method == "Cash Drawer":
            movement_id = create_drawer_cash_advance_movement(
                conn, cash_advance_id, actor=str(user.get("display_name") or "System"), commit=False,
            )
            if movement_id is None:
                raise HTTPException(status_code=409, detail="Cash drawer movement could not be linked.")
        event = build_cash_advance_release_payload(conn, cash_advance_id)
        enqueue_event(
            conn,
            destination="accounting",
            event_type=event["event_type"],
            external_source=event["external_source"],
            external_id=event["external_id"],
            source_type="Cash Advance",
            source_id=cash_advance_id,
            payload=event,
            schema_ready=True,
        )
        conn.commit()
        return {"ok": True, "already_recorded": False, "cash_advance_id": cash_advance_id}
    except Exception:
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
        if str(advance.get("released_at") or "").strip():
            raise HTTPException(status_code=409, detail="A disbursed advance cannot be cancelled as if funds were never issued.")
        _transition_cash_advance(conn, advance=advance, target="Cancelled", allowed_from={"Pending", "Rejected", "Active"}, user=user, reason=payload.reason, reason_required=True)
        response = _transition_response(conn, cash_advance_id)
        conn.commit()
        return response
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
