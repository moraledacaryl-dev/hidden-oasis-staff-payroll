from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user, totals
from api.schedule_history_controls import router as schedule_history_router
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.payroll_engine import compute_payroll

router = APIRouter(prefix="/api/v1")
router.include_router(schedule_history_router, prefix="")

PAYROLL_ITEM_COLS = [
    "employee_id", "regular_hours", "regular_pay", "approved_ot_hours", "ot_pay",
    "night_diff_hours", "night_diff_pay", "holiday_pay", "paid_leave_days",
    "paid_leave_pay", "freelance_pay", "other_earnings", "gross_pay",
    "late_minutes", "undertime_minutes", "unpaid_absence_days", "sss_ee",
    "philhealth_ee", "pagibig_ee", "sss_er", "sss_ec", "philhealth_er",
    "pagibig_er", "tax", "cash_advance_deduction", "other_deductions",
    "total_deductions", "net_pay", "warnings",
]


class RevisionPayload(BaseModel):
    run_label: str | None = None


def now_iso(conn) -> str:
    return str(conn.execute("SELECT datetime('now','localtime')").fetchone()[0])


def item_dict(item: Any) -> dict[str, Any]:
    data = asdict(item) if is_dataclass(item) else dict(item)
    data["warnings"] = "\n".join(data.get("warnings") or [])
    return data


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


@router.get("/payroll/runs/{run_id}/change-delta")
def payroll_run_change_delta(run_id: int, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        if not table_exists(conn, "schedule_change_logs"):
            return {"ok": True, "run_id": run_id, "changed": False, "change_count": 0, "changes": []}
        changes = fetchall(conn, """
            SELECT *
            FROM schedule_change_logs
            WHERE date(work_date) BETWEEN date(?) AND date(?)
              AND datetime(changed_at) > datetime(?)
              AND undone_at IS NULL
            ORDER BY changed_at DESC, id DESC
        """, (run["period_start"], run["period_end"], run["created_at"]))
        return {"ok": True, "run_id": run_id, "changed": bool(changes), "change_count": len(changes), "changes": changes}
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/save-revision")
def save_payroll_revision(run_id: int, payload: RevisionPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        base_label = payload.run_label or f"{run['run_label']} Revision"
        rows = fetchall(conn, "SELECT run_label FROM payroll_runs WHERE period_start=? AND period_end=?", (run["period_start"], run["period_end"]))
        used = {row["run_label"] for row in rows}
        label = base_label
        n = 2
        while label in used:
            label = f"{base_label} {n}"
            n += 1
        ts = now_iso(conn)
        cur = conn.execute("""
            INSERT INTO payroll_runs(period_start, period_end, payout_date, run_label, status, prepared_by, validation_summary, created_at)
            VALUES (?, ?, ?, ?, 'Draft', ?, ?, ?)
        """, (run["period_start"], run["period_end"], run["payout_date"], label, user.get("display_name"), f"Revision of payroll run #{run_id}.", ts))
        new_run_id = int(cur.lastrowid)
        for result in compute_payroll(conn, run["period_start"], run["period_end"]):
            data = item_dict(result)
            values = [new_run_id] + [data.get(c, 0) for c in PAYROLL_ITEM_COLS] + [ts]
            conn.execute(
                f"INSERT INTO payroll_items (payroll_run_id,{','.join(PAYROLL_ITEM_COLS)},created_at) VALUES ({','.join('?' for _ in values)})",
                values,
            )
        conn.commit()
        new_run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (new_run_id,)) or {}
        new_run["totals"] = totals(conn, new_run_id)
        return {"ok": True, "run": new_run, "mode": "revision_saved_from_current_schedule_actuals"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
