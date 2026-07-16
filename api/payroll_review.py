from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api.payroll_drafts import must_be_payroll_user, totals
from core.db import DB_PATH, fetchall, fetchone, get_conn

router = APIRouter(prefix="/api/v1")

PAYROLL_ITEM_FIELDS = [
    "id", "employee_id", "regular_hours", "regular_pay", "approved_ot_hours", "ot_pay",
    "night_diff_hours", "night_diff_pay", "holiday_pay", "paid_leave_days", "paid_leave_pay",
    "freelance_pay", "other_earnings", "gross_pay", "late_minutes", "undertime_minutes",
    "unpaid_absence_days", "sss_ee", "philhealth_ee", "pagibig_ee", "sss_er", "sss_ec",
    "philhealth_er", "pagibig_er", "tax", "cash_advance_deduction", "other_deductions",
    "total_deductions", "net_pay", "warnings", "created_at",
]

DATE_COLUMNS = ["work_date", "leave_date", "date", "day"]
START_COLUMNS = ["start_date", "date_start", "from_date", "leave_start"]
END_COLUMNS = ["end_date", "date_end", "to_date", "leave_end"]
TYPE_COLUMNS = ["leave_type", "type", "category", "leave_name", "name"]
TYPE_ID_COLUMNS = ["leave_type_id", "type_id", "category_id", "leave_id"]
DAYS_COLUMNS = ["days", "leave_days", "paid_leave_days", "duration_days", "number_of_days"]
STATUS_COLUMNS = ["status", "approval_status", "state"]


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _fmt_date(value: date) -> str:
    return value.strftime("%b %-d, %Y")


def _pick(columns: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_columns(conn, table_name: str) -> set[str]:
    return {str(row.get("name")) for row in fetchall(conn, f"PRAGMA table_info({_quote(table_name)})") if row.get("name")}


def _leave_tables(conn) -> list[tuple[str, set[str]]]:
    tables = fetchall(conn, "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) LIKE '%leave%'")
    results: list[tuple[str, set[str]]] = []
    for table in tables:
        name = table.get("name")
        if not name:
            continue
        cols = _table_columns(conn, str(name))
        if "employee_id" in cols:
            results.append((str(name), cols))
    return results


def _leave_type_lookup(conn) -> dict[int, str]:
    tables = fetchall(conn, "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) IN ('leave_types','leave_type')")
    lookup: dict[int, str] = {}
    for table in tables:
        table_name = str(table.get("name"))
        cols = _table_columns(conn, table_name)
        if "id" not in cols:
            continue
        name_col = _pick(cols, ["name", "leave_type", "type", "title", "label"])
        if not name_col:
            continue
        for row in fetchall(conn, f"SELECT id, {_quote(name_col)} AS leave_type_name FROM {_quote(table_name)}"):
            try:
                lookup[int(row.get("id"))] = str(row.get("leave_type_name") or "Paid Leave")
            except (TypeError, ValueError):
                continue
    return lookup


def _fetch_leave_rows(conn, employee_id: int, period_start: str, period_end: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    type_lookup = _leave_type_lookup(conn)
    for table, columns in _leave_tables(conn):
        start_col = _pick(columns, START_COLUMNS)
        end_col = _pick(columns, END_COLUMNS)
        single_col = _pick(columns, DATE_COLUMNS)
        type_col = _pick(columns, TYPE_COLUMNS)
        type_id_col = _pick(columns, TYPE_ID_COLUMNS)
        days_col = _pick(columns, DAYS_COLUMNS)
        status_col = _pick(columns, STATUS_COLUMNS)
        select_cols = ["employee_id"]
        for col in [start_col, end_col, single_col, type_col, type_id_col, days_col, status_col]:
            if col and col not in select_cols:
                select_cols.append(col)
        if start_col and end_col:
            where = f"employee_id=? AND date({_quote(end_col)}) >= date(?) AND date({_quote(start_col)}) <= date(?)"
            params: tuple[Any, ...] = (employee_id, period_start, period_end)
        elif single_col:
            where = f"employee_id=? AND date({_quote(single_col)}) BETWEEN date(?) AND date(?)"
            params = (employee_id, period_start, period_end)
        else:
            continue
        if status_col:
            where += f" AND lower(coalesce({_quote(status_col)}, '')) NOT IN ('rejected','declined','cancelled','canceled','void')"
        sql = f"SELECT {', '.join(_quote(col) for col in select_cols)} FROM {_quote(table)} WHERE {where} ORDER BY { _quote(start_col or single_col or 'employee_id') }"
        for row in fetchall(conn, sql, params):
            if type_col and row.get(type_col):
                leave_type = str(row.get(type_col))
            elif type_id_col and row.get(type_id_col) is not None:
                try:
                    leave_type = type_lookup.get(int(row.get(type_id_col)), "Paid Leave")
                except (TypeError, ValueError):
                    leave_type = "Paid Leave"
            else:
                leave_type = "Paid Leave"
            start_date = _parse_date(row.get(start_col or single_col))
            end_date = _parse_date(row.get(end_col or single_col)) or start_date
            if not start_date or not end_date:
                continue
            days = row.get(days_col) if days_col else None
            rows.append({"type": leave_type, "start": start_date, "end": end_date, "days": days})
    return rows


def _leave_summaries(conn, employee_id: int, period_start: str, period_end: str) -> list[str]:
    rows = _fetch_leave_rows(conn, employee_id, period_start, period_end)
    if not rows:
        return []
    rows.sort(key=lambda row: (str(row["type"]).lower(), row["start"], row["end"]))
    merged: list[dict[str, Any]] = []
    for row in rows:
        current = merged[-1] if merged else None
        if current and current["type"] == row["type"] and row["start"] <= current["end"] + timedelta(days=1):
            current["end"] = max(current["end"], row["end"])
            current["days"] = None
        else:
            merged.append(dict(row))
    summaries: list[str] = []
    for row in merged:
        start_date = row["start"]
        end_date = row["end"]
        if row.get("days") not in (None, ""):
            try:
                day_count = float(row["days"])
            except (TypeError, ValueError):
                day_count = (end_date - start_date).days + 1
        else:
            day_count = (end_date - start_date).days + 1
        days_text = f"{day_count:g} day" + ("" if day_count == 1 else "s")
        date_text = _fmt_date(start_date) if start_date == end_date else f"{_fmt_date(start_date)}–{_fmt_date(end_date)}"
        summaries.append(f"{row['type']}: {date_text} ({days_text})")
    return summaries


def _cash_advance_details(conn, run_id: int, employee_id: int) -> list[dict[str, Any]]:
    rows = fetchall(
        conn,
        """
        SELECT
            r.id AS repayment_id,
            r.cash_advance_id,
            r.amount AS paid_this_payroll,
            COALESCE(r.repayment_date, r.payment_date) AS repayment_date,
            ca.amount AS original_amount,
            COALESCE(ca.remaining_balance, ca.outstanding_balance, ca.amount, 0) AS current_balance,
            ca.status,
            ca.advance_date,
            ca.reason
        FROM cash_advance_repayments r
        LEFT JOIN cash_advances ca ON ca.id = r.cash_advance_id
        WHERE r.payroll_run_id=?
          AND r.employee_id=?
          AND COALESCE(r.active,1)=1
        ORDER BY ca.advance_date, r.cash_advance_id, r.id
        """,
        (run_id, employee_id),
    )
    details: list[dict[str, Any]] = []
    for row in rows:
        original = round(float(row.get("original_amount") or 0), 2)
        paid = round(float(row.get("paid_this_payroll") or 0), 2)
        balance = round(float(row.get("current_balance") or 0), 2)
        details.append({
            "cash_advance_id": row.get("cash_advance_id"),
            "repayment_id": row.get("repayment_id"),
            "advance_date": row.get("advance_date"),
            "repayment_date": row.get("repayment_date"),
            "original_amount": original,
            "paid_this_payroll": paid,
            "current_balance": balance,
            "balance_after_this_payroll": balance,
            "status": row.get("status") or ("Fully Paid" if balance <= 0 else "Active"),
            "reason": row.get("reason"),
        })
    return details


def _cash_advance_audit(conn, run_id: int, period_start: str, period_end: str) -> dict[str, Any]:
    expected_rows = fetchall(
        conn,
        """
        SELECT
            ca.employee_id,
            e.full_name,
            COUNT(*) AS period_advances,
            SUM(
                CASE
                    WHEN COALESCE(ca.deduction_per_payroll, ca.repayment_per_cutoff, 0) <= 0 THEN 0
                    WHEN COALESCE(ca.remaining_balance, ca.outstanding_balance, ca.amount, 0)
                         < COALESCE(ca.deduction_per_payroll, ca.repayment_per_cutoff, 0)
                    THEN COALESCE(ca.remaining_balance, ca.outstanding_balance, ca.amount, 0)
                    ELSE COALESCE(ca.deduction_per_payroll, ca.repayment_per_cutoff, 0)
                END
            ) AS expected_deduction
        FROM cash_advances ca
        LEFT JOIN employees e ON e.id = ca.employee_id
        WHERE (
                COALESCE(ca.remaining_balance, ca.outstanding_balance, ca.amount, 0) > 0
                OR r.id IS NOT NULL
              )
          AND COALESCE(ca.status, '') NOT IN ('Cancelled','Rejected','Void','Voided')
          AND (
                r.id IS NOT NULL
                OR COALESCE(ca.status, '') NOT IN ('Pending')
              )
          AND lower(COALESCE(ca.repayment_method, 'Payroll deduction')) LIKE '%payroll%'
          AND date(COALESCE(ca.advance_date, ca.request_date)) BETWEEN date(?) AND date(?)
        GROUP BY ca.employee_id, e.full_name
        ORDER BY e.full_name
        """,
        (period_start, period_end),
    )
    items = fetchall(
        conn,
        """
        SELECT employee_id, COALESCE(cash_advance_deduction,0) AS applied
        FROM payroll_items
        WHERE payroll_run_id=?
        """,
        (run_id,),
    )
    applied_by_employee = {int(row.get("employee_id") or 0): float(row.get("applied") or 0) for row in items}
    rows: list[dict[str, Any]] = []
    expected_total = 0.0
    applied_total = 0.0
    issue_count = 0
    for row in expected_rows:
        employee_id = int(row.get("employee_id") or 0)
        expected = round(float(row.get("expected_deduction") or 0), 2)
        applied = round(applied_by_employee.get(employee_id, 0.0), 2)
        expected_total += expected
        applied_total += applied
        if applied + 0.005 < expected:
            status = "MISSING/LOW"
            issue_count += 1
        elif applied > expected + 0.005:
            status = "OVER"
            issue_count += 1
        else:
            status = "OK"
        rows.append({
            "employee_id": employee_id,
            "name": row.get("full_name") or f"Employee {employee_id}",
            "period_advances": int(row.get("period_advances") or 0),
            "expected": expected,
            "applied": applied,
            "status": status,
        })
    return {
        "expected_total": round(expected_total, 2),
        "applied_total": round(applied_total, 2),
        "issue_count": issue_count,
        "rows": rows,
        "status": "OK" if issue_count == 0 else "Needs Review",
    }



def _cash_advance_run_check(
    conn,
    run_id: int,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    run = fetchone(
        conn,
        "SELECT status FROM payroll_runs WHERE id=?",
        (run_id,),
    ) or {}

    run_status = str(run.get("status") or "")
    paid_run = run_status in {
        "Paid",
        "Locked",
        "Released",
    }

    # Exact manually selected cash advance allocations for this run.
    explicit_rows = fetchall(
        conn,
        """
        SELECT
            employee_id,
            cash_advance_id,
            COALESCE(cash_advance_amount,0) AS amount
        FROM payroll_item_adjustments
        WHERE payroll_run_id=?
          AND cash_advance_id IS NOT NULL
          AND COALESCE(cash_advance_amount,0)>0
        """,
        (run_id,),
    )

    explicit_by_advance = {
        int(row.get("cash_advance_id") or 0): round(
            float(row.get("amount") or 0),
            2,
        )
        for row in explicit_rows
    }

    explicit_by_employee: dict[int, float] = {}
    for row in explicit_rows:
        employee_id = int(row.get("employee_id") or 0)
        explicit_by_employee[employee_id] = round(
            explicit_by_employee.get(employee_id, 0.0)
            + float(row.get("amount") or 0),
            2,
        )

    payroll_items = fetchall(
        conn,
        """
        SELECT
            employee_id,
            COALESCE(cash_advance_deduction,0) AS deduction
        FROM payroll_items
        WHERE payroll_run_id=?
        """,
        (run_id,),
    )

    # Any amount not tied to an explicit manual selection is an automatic
    # payroll deduction. Allocate it FIFO across eligible advances.
    automatic_remaining = {
        int(row.get("employee_id") or 0): round(
            max(
                0.0,
                float(row.get("deduction") or 0)
                - explicit_by_employee.get(
                    int(row.get("employee_id") or 0),
                    0.0,
                ),
            ),
            2,
        )
        for row in payroll_items
    }

    advance_rows = fetchall(
        conn,
        """
        SELECT
            ca.id AS cash_advance_id,
            ca.employee_id,
            e.full_name AS name,
            COALESCE(
                ca.advance_date,
                ca.request_date
            ) AS advance_date,
            COALESCE(ca.amount,0) AS original_amount,
            COALESCE(
                ca.remaining_balance,
                ca.outstanding_balance,
                ca.amount,
                0
            ) AS current_balance,
            COALESCE(
                ca.deduction_per_payroll,
                ca.repayment_per_cutoff,
                ca.custom_next_deduction,
                0
            ) AS scheduled_deduction,
            COALESCE(r.amount,0) AS posted_repayment,
            r.id AS repayment_id,
            ca.reason,
            COALESCE(ca.status,'') AS advance_status
        FROM cash_advances ca
        LEFT JOIN employees e
          ON e.id=ca.employee_id
        LEFT JOIN cash_advance_repayments r
          ON r.cash_advance_id=ca.id
         AND r.payroll_run_id=?
         AND COALESCE(r.active,1)=1
        WHERE COALESCE(ca.status,'') NOT IN (
                'Cancelled',
                'Rejected',
                'Void',
                'Voided'
              )
          AND lower(
                COALESCE(
                    ca.repayment_method,
                    'Payroll deduction'
                )
              ) LIKE '%payroll%'
          AND date(
                COALESCE(
                    ca.advance_date,
                    ca.request_date
                )
              ) <= date(?)
          AND (
                COALESCE(
                    ca.remaining_balance,
                    ca.outstanding_balance,
                    ca.amount,
                    0
                ) > 0
                OR r.id IS NOT NULL
                OR ca.id IN (
                    SELECT cash_advance_id
                    FROM payroll_item_adjustments
                    WHERE payroll_run_id=?
                      AND cash_advance_id IS NOT NULL
                      AND COALESCE(cash_advance_amount,0)>0
                )
              )
        ORDER BY
            e.full_name,
            date(
                COALESCE(
                    ca.advance_date,
                    ca.request_date
                )
            ),
            ca.id
        """,
        (run_id, period_end, run_id),
    )

    rows: list[dict[str, Any]] = []
    expected_total = 0.0
    applied_total = 0.0
    issue_count = 0

    for row in advance_rows:
        advance_id = int(
            row.get("cash_advance_id") or 0
        )
        employee_id = int(
            row.get("employee_id") or 0
        )

        posted = round(
            float(row.get("posted_repayment") or 0),
            2,
        )
        current_balance = round(
            float(row.get("current_balance") or 0),
            2,
        )

        # A posted repayment has already reduced the live balance.
        balance_before_run = round(
            current_balance + posted,
            2,
        )

        scheduled = round(
            float(row.get("scheduled_deduction") or 0),
            2,
        )

        selected_explicitly = advance_id in explicit_by_advance

        if paid_run:
            # Historical paid runs are validated against posted repayments.
            applied = posted
            expected = round(
                min(balance_before_run, scheduled)
                if posted > 0 and scheduled > 0
                else posted,
                2,
            )
        elif selected_explicitly:
            # Manual adjustment selected this exact cash advance.
            applied = round(
                min(
                    explicit_by_advance[advance_id],
                    balance_before_run,
                ),
                2,
            )
            expected = applied
        else:
            # Automatic deductions are allocated FIFO. An open advance that
            # receives no allocation remains visible as NOT SELECTED.
            remaining = automatic_remaining.get(
                employee_id,
                0.0,
            )
            applied = round(
                min(
                    remaining,
                    balance_before_run,
                    scheduled,
                )
                if remaining > 0 and scheduled > 0
                else 0.0,
                2,
            )
            automatic_remaining[employee_id] = round(
                max(0.0, remaining - applied),
                2,
            )
            expected = applied

        if not paid_run and applied <= 0:
            status = "NOT SELECTED"
            issue = False
        elif paid_run and posted <= 0:
            status = "NOT APPLIED"
            issue = True
        elif applied + 0.005 < expected:
            status = "PARTIAL"
            issue = True
        elif applied > expected + 0.005:
            status = "OVER"
            issue = True
        else:
            # For unpaid runs, APPLIED means included in this payroll only.
            status = "APPLIED"
            issue = False

        if issue:
            issue_count += 1

        expected_total += expected
        applied_total += applied

        balance_after_run = (
            current_balance
            if paid_run
            else max(
                0.0,
                balance_before_run - applied,
            )
        )

        rows.append({
            "employee_id": employee_id,
            "name": (
                row.get("name")
                or f"Employee {employee_id}"
            ),
            "cash_advance_id": advance_id,
            "repayment_id": row.get("repayment_id"),
            "advance_date": row.get("advance_date"),
            "original_amount": round(
                float(row.get("original_amount") or 0),
                2,
            ),
            "balance_before_run": balance_before_run,
            "expected": expected,
            "applied": applied,
            "balance_after_run": round(
                balance_after_run,
                2,
            ),
            "status": status,
            "advance_status": row.get(
                "advance_status"
            ),
            "reason": row.get("reason"),
        })

    return {
        "expected_total": round(
            expected_total,
            2,
        ),
        "applied_total": round(
            applied_total,
            2,
        ),
        "issue_count": issue_count,
        "status": (
            "OK"
            if issue_count == 0
            else "Needs Review"
        ),
        "rows": rows,
        "source": (
            "posted_repayments"
            if paid_run
            else "current_run_deductions"
        ),
    }


@router.get("/payroll/runs/{run_id}/review")
def review_payroll_run(
    run_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    must_be_payroll_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found.")
        items = fetchall(conn, "SELECT * FROM payroll_items WHERE payroll_run_id=? ORDER BY employee_id", (run_id,))
        employees = fetchall(conn, "SELECT * FROM employees")
        employee_by_id = {int(row.get("id")): row for row in employees if row.get("id") is not None}
        normalized_items = []
        period_start = str(run.get("period_start"))
        period_end = str(run.get("period_end"))
        for item in items:
            employee_id = int(item.get("employee_id") or 0)
            employee = employee_by_id.get(employee_id, {})
            full_name = employee.get("full_name") or employee.get("name") or employee.get("employee_name") or f"Employee {item.get('employee_id')}"
            row = {field: item.get(field) for field in PAYROLL_ITEM_FIELDS}
            row["employee_name"] = full_name
            row["department"] = employee.get("department") or employee.get("department_name") or "Unassigned"
            row["payroll_run_id"] = run_id
            row["leave_summary"] = _leave_summaries(conn, employee_id, period_start, period_end)
            row["cash_advance_details"] = _cash_advance_details(conn, run_id, employee_id)
            normalized_items.append(row)
        run["totals"] = totals(conn, run_id)
        return {
            "ok": True,
            "run": run,
            "items": normalized_items,
            "cash_advance_audit": _cash_advance_run_check(conn, run_id, period_start, period_end),
            "mode": "review_only_not_released",
        }
    finally:
        conn.close()
