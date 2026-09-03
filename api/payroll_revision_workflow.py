from api.payroll_revision_service import ControlledRevisionPayload, ensure_workflow_schema, is_paid_run

from fastapi import APIRouter, Header, HTTPException
from typing import Any

from api.payroll_adjustments import ensure_schema as ensure_adjustment_schema
from api.payroll_drafts import must_be_payroll_user, totals
from api.payroll_revision_controls import PAYROLL_ITEM_COLS, changes_for_run, ensure_revision_schema, item_dict, now_iso
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.money import money
from core.payroll_fractional_leave import compute_payroll_with_fractional_leave

router = APIRouter(prefix="/api/v1")


def carry_forward_manual_values(conn, source_run_id: int, new_run_id: int, treatment: str, stamp: str, actor: str | None) -> int:
    source_adjustments = fetchall(conn, "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=?", (source_run_id,))
    new_items = {int(row["employee_id"]): row for row in fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=?", (new_run_id,))}
    copied = 0

    if treatment == "replace_unpaid":
        conn.execute(
            """
            UPDATE cash_advance_repayments
            SET active=0,reversed_by=?,reversed_at=?,reversal_reason='Transferred to replacement payroll revision'
            WHERE payroll_run_id=? AND source='Payroll' AND COALESCE(active,1)=1
            """,
            (actor, stamp, source_run_id),
        )

    for adjustment in source_adjustments:
        employee_id = int(adjustment["employee_id"])
        item = new_items.get(employee_id)
        if not item:
            continue

        earning = money(adjustment.get("additional_earning") or 0)
        other = money(adjustment.get("other_deduction") or 0)
        cash = money(adjustment.get("cash_advance_amount") or 0)

        base_gross = money(item.get("gross_pay") or 0)
        base_total = money(item.get("total_deductions") or 0)
        auto_cash = money(item.get("cash_advance_deduction") or 0)

        gross = money(base_gross + earning)
        total_deductions = money(base_total - auto_cash + other + cash)
        net_pay = money(gross - total_deductions)

        conn.execute(
            """
            UPDATE payroll_items
            SET other_earnings=COALESCE(other_earnings,0)+?,
                gross_pay=?,
                cash_advance_deduction=?,
                other_deductions=COALESCE(other_deductions,0)+?,
                total_deductions=?,
                net_pay=?
            WHERE id=?
            """,
            (earning, gross, cash, other, total_deductions, net_pay, item["id"]),
        )

        conn.execute(
            """
            INSERT INTO payroll_item_adjustments(
                payroll_run_id,payroll_item_id,employee_id,additional_earning,
                additional_earning_note,other_deduction,other_deduction_note,
                cash_advance_id,cash_advance_amount,created_by,created_at,updated_by,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                new_run_id,
                item["id"],
                employee_id,
                earning,
                adjustment.get("additional_earning_note"),
                other,
                adjustment.get("other_deduction_note"),
                adjustment.get("cash_advance_id"),
                cash,
                actor,
                stamp,
                actor,
                stamp,
            ),
        )
        copied += 1

    return copied


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
        ensure_adjustment_schema(conn)
        ensure_revision_schema(conn)
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")

        paid = is_paid_run(run)
        if paid and payload.treatment != "adjust_paid":
            raise HTTPException(status_code=409, detail="This payroll was already paid. Create an adjustment revision instead.")
        if not paid and payload.treatment != "replace_unpaid":
            raise HTTPException(status_code=409, detail="This payroll is not yet paid. Use Replace unpaid run.")

        existing = fetchone(
            conn,
            "SELECT id,status FROM payroll_runs WHERE revision_of_run_id=? AND status NOT IN ('Cancelled','Voided') ORDER BY id DESC LIMIT 1",
            (run_id,),
        )
        if existing:
            raise HTTPException(status_code=409, detail=f"Run #{run_id} already has active revision run #{existing['id']}.")

        changes, baseline_created_at, _previous, _mode = changes_for_run(conn, run)
        base_label = (payload.run_label or f"{run['run_label']} Revision").strip()
        used = {
            str(row.get("run_label") or "")
            for row in fetchall(
                conn,
                "SELECT run_label FROM payroll_runs WHERE period_start=? AND period_end=?",
                (run["period_start"], run["period_end"]),
            )
        }
        label = base_label
        suffix = 2
        while label in used:
            label = f"{base_label} {suffix}"
            suffix += 1

        stamp = now_iso(conn)
        cur = conn.execute(
            """
            INSERT INTO payroll_runs(
                period_start,period_end,payout_date,run_label,status,prepared_by,
                validation_summary,created_at,revision_of_run_id,revision_reason,revision_treatment
            ) VALUES(?,?,?,?,'Draft',?,?,?,?,?,?)
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

        for result in compute_payroll_with_fractional_leave(conn, run["period_start"], run["period_end"]):
            data = item_dict(result)
            values = [new_run_id] + [data.get(column, 0) for column in PAYROLL_ITEM_COLS] + [stamp]
            conn.execute(
                f"INSERT INTO payroll_items (payroll_run_id,{','.join(PAYROLL_ITEM_COLS)},created_at) VALUES ({','.join('?' for _ in values)})",
                values,
            )

        copied_adjustments = carry_forward_manual_values(
            conn,
            run_id,
            new_run_id,
            payload.treatment,
            stamp,
            user.get("display_name"),
        )

        for change in changes:
            conn.execute(
                "INSERT OR IGNORE INTO payroll_revision_change_links(payroll_run_id,change_log_id,created_at) VALUES(?,?,?)",
                (new_run_id, int(change["id"]), stamp),
            )

        summary = {"employees": 0, "additional_pay": 0.0, "recoverable": 0.0, "net_adjustment": 0.0}
        if payload.treatment == "adjust_paid":
            original_items = {
                int(row["employee_id"]): row
                for row in fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=?", (run_id,))
            }
            revised_items = {
                int(row["employee_id"]): row
                for row in fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=?", (new_run_id,))
            }
            for employee_id in sorted(set(original_items) | set(revised_items)):
                original_net = money((original_items.get(employee_id) or {}).get("net_pay") or 0)
                revised_net = money((revised_items.get(employee_id) or {}).get("net_pay") or 0)
                difference = money(revised_net - original_net)
                direction = "Additional pay" if difference > 0 else "Recoverable" if difference < 0 else "No change"
                if difference > 0:
                    summary["additional_pay"] += difference
                elif difference < 0:
                    summary["recoverable"] += abs(difference)
                if difference != 0:
                    summary["employees"] += 1
                    summary["net_adjustment"] += difference
                conn.execute(
                    "INSERT INTO payroll_revision_adjustments(revision_run_id,original_run_id,employee_id,original_net_pay,revised_net_pay,adjustment_amount,adjustment_direction,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (new_run_id, run_id, employee_id, original_net, revised_net, difference, direction, stamp),
                )
            summary = {key: money(value) if isinstance(value, float) else value for key, value in summary.items()}
        else:
            conn.execute("UPDATE payroll_runs SET superseded_by_run_id=? WHERE id=?", (new_run_id, run_id))

        conn.commit()
        new_run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (new_run_id,)) or {}
        new_run["totals"] = totals(conn, new_run_id)
        return {
            "ok": True,
            "run": new_run,
            "linked_change_count": len(changes),
            "copied_adjustment_count": copied_adjustments,
            "treatment": payload.treatment,
            "adjustment_summary": summary,
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
            "SELECT pra.*,e.full_name,e.employee_code FROM payroll_revision_adjustments pra LEFT JOIN employees e ON e.id=pra.employee_id WHERE pra.revision_run_id=? ORDER BY e.full_name,pra.employee_id",
            (run_id,),
        )
        return {"ok": True, "run": run, "items": items}
    finally:
        conn.close()
