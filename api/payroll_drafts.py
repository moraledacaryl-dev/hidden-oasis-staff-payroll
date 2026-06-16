from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.payroll_engine import compute_payroll
from core.quality import build_payroll_preflight_checks, summarize_checks

router = APIRouter(prefix="/api/v1")

class PayrollDraftRequest(BaseModel):
    period_start: date
    period_end: date
    payout_date: date
    run_label: str = Field(default="Semi-monthly")


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def role_key(role: str | None) -> str:
    text = (role or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"owner", "admin", "administrator"}:
        return "owner"
    if text in {"payroll", "payroll_admin", "hr", "hr_payroll"}:
        return "payroll"
    return "staff"


def secret() -> str:
    return os.getenv("STAFF_PAYROLL_SESSION_SECRET") or os.getenv("STAFF_PAYROLL_API_KEY") or "dev-only-change-staff-payroll-session-secret"


def b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def must_be_payroll_user(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    expected_key = os.getenv("STAFF_PAYROLL_API_KEY")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        body, signature = authorization.removeprefix("Bearer ").strip().split(".", 1)
        expected = hmac.new(secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(b64decode(signature), expected):
            raise ValueError("bad signature")
        payload = json.loads(b64decode(body).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()):
            raise ValueError("expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    conn = get_conn(DB_PATH)
    try:
        user = fetchone(conn, "SELECT * FROM app_users WHERE id=? AND active=1", (payload.get("sub"),))
    finally:
        conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists or is inactive.")
    user["role_key"] = role_key(user.get("role"))
    if user["role_key"] not in {"owner", "payroll"}:
        raise HTTPException(status_code=403, detail="Payroll draft actions require owner or payroll role.")
    return user


def item_dict(item: Any) -> dict[str, Any]:
    data = asdict(item) if is_dataclass(item) else dict(item)
    data["warnings"] = "\n".join(data.get("warnings") or [])
    return data


def totals(conn: Any, run_id: int) -> dict[str, Any]:
    row = fetchone(conn, "SELECT COUNT(*) employees, COALESCE(SUM(gross_pay),0) gross_pay, COALESCE(SUM(net_pay),0) net_pay, COALESCE(SUM(total_deductions),0) total_deductions FROM payroll_items WHERE payroll_run_id=?", (run_id,)) or {}
    return {"employees": int(row.get("employees") or 0), "gross_pay": round(float(row.get("gross_pay") or 0), 2), "net_pay": round(float(row.get("net_pay") or 0), 2), "total_deductions": round(float(row.get("total_deductions") or 0), 2)}


@router.get("/payroll/runs")
def list_payroll_runs(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> list[dict[str, Any]]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        rows = fetchall(conn, "SELECT * FROM payroll_runs ORDER BY created_at DESC, id DESC LIMIT 50")
        for row in rows:
            row["totals"] = totals(conn, int(row["id"]))
        return rows
    finally:
        conn.close()


@router.post("/payroll/runs/draft")
def create_payroll_draft(payload: PayrollDraftRequest, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    start = payload.period_start.isoformat()
    end = payload.period_end.isoformat()
    label = payload.run_label.strip() or "Semi-monthly"
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="End date cannot be before start date.")
    conn = get_conn(DB_PATH)
    try:
        existing = fetchone(conn, "SELECT id FROM payroll_runs WHERE period_start=? AND period_end=? AND run_label=?", (start, end, label))
        if existing:
            raise HTTPException(status_code=409, detail="Payroll run already exists for this period and label.")
        checks = build_payroll_preflight_checks(conn, start, end)
        blockers = [c for c in checks if c.get("severity") == "Blocker"]
        if blockers:
            raise HTTPException(status_code=409, detail={"message": "Draft blocked by payroll QA blockers.", "checks": checks})
        ts = now_iso()
        cur = conn.execute("INSERT INTO payroll_runs (period_start, period_end, payout_date, run_label, status, prepared_by, validation_summary, created_at) VALUES (?, ?, ?, ?, 'Draft', ?, ?, ?)", (start, end, payload.payout_date.isoformat(), label, user.get("display_name"), summarize_checks(checks), ts))
        run_id = int(cur.lastrowid)
        cols = ["employee_id", "regular_hours", "regular_pay", "approved_ot_hours", "ot_pay", "night_diff_hours", "night_diff_pay", "holiday_pay", "paid_leave_days", "paid_leave_pay", "freelance_pay", "other_earnings", "gross_pay", "late_minutes", "undertime_minutes", "unpaid_absence_days", "sss_ee", "philhealth_ee", "pagibig_ee", "sss_er", "sss_ec", "philhealth_er", "pagibig_er", "tax", "cash_advance_deduction", "other_deductions", "total_deductions", "net_pay", "warnings"]
        for result in compute_payroll(conn, start, end):
            data = item_dict(result)
            values = [run_id] + [data.get(c, 0) for c in cols] + [ts]
            conn.execute(f"INSERT INTO payroll_items (payroll_run_id,{','.join(cols)},created_at) VALUES ({','.join('?' for _ in values)})", values)
        conn.commit()
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        run["totals"] = totals(conn, run_id)
        return {"ok": True, "run": run, "checks": checks, "mode": "draft_saved_not_released"}
    except HTTPException:
        conn.rollback(); raise
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/approve")
def approve_payroll_run(run_id: int, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Only owner can approve payroll.")
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        if run.get("status") != "For Owner Review":
            raise HTTPException(status_code=409, detail="Only owner-review runs can be approved.")
        conn.execute("UPDATE payroll_runs SET status='Approved', approved_by=?, approved_at=? WHERE id=?", (user.get("display_name"), now_iso(), run_id))
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        updated["totals"] = totals(conn, run_id)
        return {"ok": True, "run": updated, "mode": "approved_not_released"}
    finally:
        conn.close()
