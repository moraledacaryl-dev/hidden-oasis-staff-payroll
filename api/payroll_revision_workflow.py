from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.payroll_drafts import must_be_payroll_user, totals
from api.payroll_revision_controls import (
    PAYROLL_ITEM_COLS,
    changes_for_run,
    ensure_revision_schema,
    item_dict,
    now_iso,
)
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.payroll_engine import compute_payroll

router = APIRouter(prefix="/api/v1")


class ControlledRevisionPayload(BaseModel):
    run_label: str | None = None
    revision_reason: str
    treatment: Literal["replace_unpaid", "adjust_paid"]


def ensure_workflow_schema(conn) -> None:
    ensure_revision_schema(conn)
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(payroll_runs)").fetchall()}
    if "revision_treatment" not in columns:
        conn.execute("ALTER TABLE payroll_runs ADD COLUMN revision_treatment TEXT")
    if "superseded_by_run_id" not in columns:
        conn.execute("ALTER TABLE payroll_runs ADD COLUMN superseded_by_run_id INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_revision_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_run_id INTEGER NOT NULL,
            original_run_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            original_net_pay REAL NOT NULL DEFAULT 0,
            revised_net_pay REAL NOT NULL DEFAULT 0,
            adjustment_amount REAL NOT NULL DEFAULT 0,
            adjustment_direction TEXT NOT NULL,
            settlement_status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            UNIQUE(revision_run_id, employee_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_revision_adjustments_run ON payroll_revision_adjustments(revision_run_id)")
    conn.commit()


def is_paid_run(run: dict[str, Any]) -> bool:
    status = str(run.get("status") or "").strip().lower()
    return bool(run.get("paid_at")) or status in {"paid", "released"}


@router.post("/payroll/runs/{run_id}/save-controlled-revision")
def save_controlled_revision(
    run_id: int,
    payload: ControlledRevisionPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    reason = payload.revision_reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A revision reason is required.")

    conn = get_conn(DB_PATH)
    try:
        ensure_workflow_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")

        paid = is_paid_run(run)
        if paid and payload.treatment != "adjust_paid":
            raise HTTPException(status_code=409, detail="This payroll was already paid. Create an adjustment revision instead of replacing it.")
        if not paid and payload.treatment != "replace_unpaid":
            raise HTTPException(status_code=409, detail="This payroll is not yet paid. Use Replace unpaid run.")

        existing_revision = fetchone(
            conn,
            "SELECT id, status FROM payroll_runs WHERE revision_of_run_id=? AND status NOT IN ('Cancelled','Voided') ORDER BY id DESC LIMIT 1",
            (run_id,),
        )
        if existing_revision:
            raise HTTPException(status_code=409, detail=f"Run #{run_id} already has active revision run #{existing_revision['id']}.")

        change_rows, baseline_created_at, _previous, _mode = changes_for_run(conn, run)
        base_label = (payload.run_label or f"{run['run_label']} Revision").strip()
        labels = fetchall(conn, "SELECT run_label FROM payroll_runs WHERE period_start=? AND period_end=?", (run["period_start"], run["period_end"]))
        used = {str(row.get("run_label") or "") for row in labels}
        label = base_label
        suffix = 2
        while label in used:
            label = f"{base_label} {suffix}"
            suffix += 1

        stamp = now_iso(conn)
        cur = conn.execute(
            """
            INSERT INTO payroll_runs(
                period_start, period_end, payout_date, run_label, status, prepared_by,
                validation_summary, created_at, revision_of_run_id, revision_reason,
                revision_treatment
            ) VALUES (?, ?, ?, ?, 'Draft', ?, ?, ?, ?, ?, ?)
            """,
            (
                run["period_start"],
                run["period_end"],
                run["payout_date"],
                label,
                user.get("display_name"),
                f"Revision of payroll run #{run_id}. Baseline created_at: {baseline_created_at}.",
                stamp,
                run_id,
                reason,
                payload.treatment,
            ),
        )
        new_run_id = int(cur.lastrowid)

        for result in compute_payroll(conn, run["period_start"], run["period_end"]):
            data = item_dict(result)
            values = [new_run_id] + [data.get(column, 0) for column in PAYROLL_ITEM_COLS] + [stamp]
            conn.execute(
                f"INSERT INTO payroll_items (payroll_run_id,{','.join(PAYROLL_ITEM_COLS)},created_at) VALUES ({','.join('?' for _ in values)})",
                values,
            )

        for change in change_rows:
            conn.execute(
                "INSERT OR IGNORE INTO payroll_revision_change_links(payroll_run_id,change_log_id,created_at) VALUES(?,?,?)",
                (new_run_id, int(change["id"]), stamp),
            )

        adjustment_summary = {"employees": 0, "additional_pay": 0.0, "recoverable": 0.0, "net_adjustment": 0.0}
        if payload.treatment == "adjust_paid":
            original_items = {int(row["employee_id"]): row for row in fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=?", (run_id,))}
            revised_items = {int(row["employee_id"]): row for row in fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=?", (new_run_id,))}
            employee_ids = sorted(set(original_items) | set(revised_items))
            for employee_id in employee_ids:
                original_net = round(float((original_items.get(employee_id) or {}).get("net_pay") or 0), 2)
                revised_net = round(float((revised_items.get(employee_id) or {}).get("net_pay") or 0), 2)
                difference = round(revised_net - original_net, 2)
                if difference > 0:
                    direction = "Additional pay"
                    adjustment_summary["additional_pay"] += difference
                elif difference < 0:
                    direction = "Recoverable"
                    adjustment_summary["recoverable"] += abs(difference)
                else:
                    direction = "No change"
                conn.execute(
                    """
                    INSERT INTO payroll_revision_adjustments(
                        revision_run_id,original_run_id,employee_id,original_net_pay,
                        revised_net_pay,adjustment_amount,adjustment_direction,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (new_run_id, run_id, employee_id, original_net, revised_net, difference, direction, stamp),
                )
                if difference != 0:
                    adjustment_summary["employees"] += 1
                    adjustment_summary["net_adjustment"] += difference
            adjustment_summary = {key: round(value, 2) if isinstance(value, float) else value for key, value in adjustment_summary.items()}
        else:
            conn.execute("UPDATE payroll_runs SET superseded_by_run_id=? WHERE id=?", (new_run_id, run_id))

        conn.commit()
        new_run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (new_run_id,)) or {}
        new_run["totals"] = totals(conn, new_run_id)
        return {
            "ok": True,
            "run": new_run,
            "linked_change_count": len(change_rows),
            "treatment": payload.treatment,
            "adjustment_summary": adjustment_summary,
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/payroll/runs/{run_id}/revision-adjustments")
def get_revision_adjustments(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        ensure_workflow_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        items = fetchall(
            conn,
            """
            SELECT pra.*,e.full_name,e.employee_code
            FROM payroll_revision_adjustments pra
            LEFT JOIN employees e ON e.id=pra.employee_id
            WHERE pra.revision_run_id=?
            ORDER BY e.full_name,pra.employee_id
            """,
            (run_id,),
        )
        return {"ok": True, "run": run, "items": items}
    finally:
        conn.close()
