from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.payroll_drafts import must_be_payroll_user, now_iso, totals
from core.db import DB_PATH, fetchall, fetchone, get_conn
from core.money import money
from core.payroll_engine import add_payroll_lines
from core.payroll_fractional_leave import apply_fractional_paid_leave_adjustments
from core.payroll_split_shift_policy import compute_payroll_per_shift
from core.quality import build_payroll_preflight_checks, summarize_checks

router = APIRouter(prefix="/api/v1")

COMPUTED_COLUMNS = [
    "regular_hours", "regular_pay", "approved_ot_hours", "ot_pay",
    "night_diff_hours", "night_diff_pay", "holiday_pay", "paid_leave_days",
    "paid_leave_pay", "freelance_pay", "other_earnings", "gross_pay",
    "late_minutes", "undertime_minutes", "unpaid_absence_days", "sss_ee",
    "philhealth_ee", "pagibig_ee", "sss_er", "sss_ec", "philhealth_er",
    "pagibig_er", "tax", "cash_advance_deduction", "other_deductions",
    "total_deductions", "net_pay", "warnings",
]


def _adjustments(conn: Any, run_id: int) -> dict[int, dict[str, Any]]:
    rows = fetchall(
        conn,
        "SELECT * FROM payroll_item_adjustments WHERE payroll_run_id=?",
        (run_id,),
    ) if fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='payroll_item_adjustments'") else []
    return {int(row["employee_id"]): row for row in rows}


def _apply_manual(result: Any, adjustment: dict[str, Any] | None) -> Any:
    if not adjustment:
        return result
    earning = money(adjustment.get("additional_earning") or 0)
    other = money(adjustment.get("other_deduction") or 0)
    cash = money(adjustment.get("cash_advance_amount") or 0)

    result.other_earnings = money(money(result.other_earnings or 0) + earning)
    result.gross_pay = money(money(result.gross_pay or 0) + earning)
    result.other_deductions = money(money(result.other_deductions or 0) + other)
    result.cash_advance_deduction = cash
    statutory = (
        money(result.sss_ee or 0)
        + money(result.philhealth_ee or 0)
        + money(result.pagibig_ee or 0)
        + money(result.tax or 0)
    )
    result.total_deductions = money(statutory + result.other_deductions + cash)
    result.net_pay = money(result.gross_pay - result.total_deductions)
    if result.net_pay < 0:
        raise HTTPException(
            status_code=422,
            detail=f"Saved manual values would make {result.full_name}'s net pay negative. Edit that employee's adjustments first.",
        )
    return result


def _table_columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _delete_draft_dependents(conn: Any, run_id: int) -> dict[str, int]:
    """Delete only data owned by a Draft run and restore references it reserved."""
    deleted: dict[str, int] = {}

    if fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='payroll_corrections'"):
        cursor = conn.execute(
            """
            UPDATE payroll_corrections
            SET status='Recorded', applied_to_run_id=NULL, applied_at=NULL
            WHERE applied_to_run_id=? AND status='Applied'
            """,
            (run_id,),
        )
        if cursor.rowcount:
            deleted["corrections_restored"] = int(cursor.rowcount)

    if "superseded_by_run_id" in _table_columns(conn, "payroll_runs"):
        conn.execute(
            "UPDATE payroll_runs SET superseded_by_run_id=NULL WHERE superseded_by_run_id=?",
            (run_id,),
        )

    tables = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    for table in tables:
        if table == "payroll_runs":
            continue
        columns = _table_columns(conn, table)
        if "payroll_run_id" not in columns:
            continue
        cursor = conn.execute(f'DELETE FROM "{table}" WHERE payroll_run_id=?', (run_id,))
        if cursor.rowcount:
            deleted[table] = int(cursor.rowcount)

    return deleted


@router.post("/payroll/runs/{run_id}/delete-draft")
def delete_draft(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        if str(run.get("status") or "") != "Draft":
            raise HTTPException(status_code=409, detail="Only Draft payroll runs can be deleted.")

        deleted = _delete_draft_dependents(conn, run_id)
        cursor = conn.execute("DELETE FROM payroll_runs WHERE id=? AND status='Draft'", (run_id,))
        if cursor.rowcount != 1:
            raise HTTPException(status_code=409, detail="Draft changed while it was being deleted. Reload and try again.")
        conn.commit()
        return {
            "ok": True,
            "deleted_run_id": run_id,
            "deleted": deleted,
            "message": f"Draft payroll run #{run_id} was deleted. You can now create it again with the correct dates.",
            "deleted_by": user.get("display_name"),
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/payroll/runs/{run_id}/recalculate")
def recalculate_draft(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        if run.get("status") != "Draft":
            raise HTTPException(status_code=409, detail="Only Draft payroll runs can be recalculated.")
        if run.get("revision_treatment") == "adjust_paid":
            raise HTTPException(status_code=409, detail="Paid difference revisions cannot be recalculated as full payroll.")

        checks = build_payroll_preflight_checks(conn, run["period_start"], run["period_end"])
        blockers = [check for check in checks if check.get("severity") == "Blocker"]
        if blockers:
            raise HTTPException(status_code=409, detail={"message": "Recalculation blocked by payroll QA blockers.", "checks": checks})

        adjustments = _adjustments(conn, run_id)
        per_shift_results = compute_payroll_per_shift(conn, run["period_start"], run["period_end"])
        per_shift_results = apply_fractional_paid_leave_adjustments(
            conn,
            per_shift_results,
            run["period_start"],
            run["period_end"],
        )
        results = [
            _apply_manual(result, adjustments.get(int(result.employee_id)))
            for result in per_shift_results
        ]
        result_by_employee = {int(result.employee_id): result for result in results}
        existing_items = fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=?", (run_id,))
        existing_by_employee = {int(item["employee_id"]): item for item in existing_items}
        stamp = now_iso()

        for employee_id, result in result_by_employee.items():
            data = result.as_db_dict()
            existing = existing_by_employee.get(employee_id)
            if existing:
                assignments = ",".join(f"{column}=?" for column in COMPUTED_COLUMNS)
                values = [data.get(column, 0) for column in COMPUTED_COLUMNS] + [existing["id"]]
                conn.execute(f"UPDATE payroll_items SET {assignments} WHERE id=?", values)
                item_id = int(existing["id"])
                conn.execute("DELETE FROM payroll_item_lines WHERE payroll_item_id=?", (item_id,))
                add_payroll_lines(conn, item_id, result)
            else:
                columns = ["payroll_run_id", "employee_id"] + COMPUTED_COLUMNS + ["created_at"]
                values = [run_id, employee_id] + [data.get(column, 0) for column in COMPUTED_COLUMNS] + [stamp]
                cursor = conn.execute(
                    f"INSERT INTO payroll_items({','.join(columns)}) VALUES({','.join('?' for _ in values)})",
                    values,
                )
                add_payroll_lines(conn, int(cursor.lastrowid), result)

        computed_employee_ids = set(result_by_employee)
        for employee_id, item in existing_by_employee.items():
            if employee_id in computed_employee_ids:
                continue
            if employee_id in adjustments:
                raise HTTPException(
                    status_code=409,
                    detail=f"Employee #{employee_id} is no longer active but still has saved manual adjustments. Resolve that employee before recalculating.",
                )
            conn.execute("DELETE FROM payroll_item_lines WHERE payroll_item_id=?", (item["id"],))
            conn.execute("DELETE FROM payroll_items WHERE id=?", (item["id"],))

        conn.execute(
            "UPDATE payroll_runs SET validation_summary=?, prepared_by=? WHERE id=?",
            (summarize_checks(checks), user.get("display_name"), run_id),
        )
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        updated["totals"] = totals(conn, run_id)
        return {
            "ok": True,
            "run": updated,
            "checks": checks,
            "preserved_manual_adjustments": len(adjustments),
            "message": "Draft recalculated from current schedule, attendance, fractional leave, OT, employee settings, and cash-advance data. Saved manual adjustments were preserved.",
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
