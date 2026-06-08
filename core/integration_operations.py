from __future__ import annotations

import json
from typing import Any

from core.db import fetchall, fetchone, now_iso
from core.integration_accounting import EXTERNAL_SOURCE, SCHEMA_VERSION, enqueue_payload
from core.quality import build_payroll_preflight_checks, summarize_checks

OPERATIONS_APP = "operations-command-center"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _event(event_type: str, external_id: str, source_record_type: str, source_record_id: int | str | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_source": EXTERNAL_SOURCE,
        "external_id": external_id,
        "event_type": event_type,
        "source_record_type": source_record_type,
        "source_record_id": source_record_id,
        "generated_at": now_iso(),
        "schema_version": SCHEMA_VERSION,
        "payload": payload,
    }


def build_operations_snapshot_payload(conn) -> dict[str, Any]:
    """One safe cross-app dashboard payload for Operations.

    This intentionally exports statuses/counts and linked identifiers only. It does
    not expose salary/rates, government IDs, payroll line amounts per employee, or
    private HR notes.
    """
    pending_attendance = fetchall(
        conn,
        """
        SELECT tl.id, tl.work_date, tl.attendance_status, tl.ot_status,
               e.employee_code, e.full_name, e.department, e.position
        FROM time_logs tl
        JOIN employees e ON e.id=tl.employee_id
        WHERE COALESCE(tl.attendance_status,'Pending') IN ('Pending','Disputed','Needs Manager','Needs Review')
           OR COALESCE(tl.ot_status,'') IN ('Pending','Review')
        ORDER BY tl.work_date DESC, e.full_name
        LIMIT 50
        """,
    )
    ot_pending = fetchall(
        conn,
        """
        SELECT tl.id, tl.work_date, tl.detected_ot_hours, tl.approved_ot_hours,
               tl.ot_status, tl.ot_reason_category, tl.ot_reason_note,
               tl.reference_occupancy, tl.reference_guest_count, tl.reference_order_count,
               tl.reference_sales, tl.reference_event_flag,
               e.employee_code, e.full_name, e.department
        FROM time_logs tl
        JOIN employees e ON e.id=tl.employee_id
        WHERE COALESCE(tl.ot_status,'Pending') IN ('Pending','Review')
          AND COALESCE(tl.detected_ot_hours,0) > 0
        ORDER BY tl.work_date DESC, e.full_name
        LIMIT 50
        """,
    )
    leave_pending = fetchall(
        conn,
        """
        SELECT lr.id, lr.start_date, lr.end_date, lr.status, lt.name AS leave_type,
               e.employee_code, e.full_name, e.department
        FROM leave_requests lr
        JOIN employees e ON e.id=lr.employee_id
        JOIN leave_types lt ON lt.id=lr.leave_type_id
        WHERE lr.status IN ('Pending','Review')
        ORDER BY lr.start_date DESC
        LIMIT 50
        """,
    )
    cash_advance_pending = fetchall(
        conn,
        """
        SELECT ca.id, ca.request_date, ca.amount, ca.status, ca.release_method,
               e.employee_code, e.full_name, e.department
        FROM cash_advances ca
        JOIN employees e ON e.id=ca.employee_id
        WHERE ca.status IN ('Requested','Pending','Approved')
        ORDER BY ca.request_date DESC
        LIMIT 50
        """,
    )
    payroll_ready = fetchall(
        conn,
        """
        SELECT id, period_start, period_end, run_label, status, payout_date,
               validation_summary
        FROM payroll_runs
        WHERE status IN ('Draft','Reviewed','Approved')
        ORDER BY id DESC
        LIMIT 20
        """,
    )
    annual_due = fetchall(
        conn,
        """
        SELECT id, employee_code, full_name, department, position, status, start_date
        FROM employees
        WHERE status IN ('Active','Probationary','Regular')
        ORDER BY full_name
        LIMIT 100
        """,
    )
    memo_pending = fetchall(
        conn,
        """
        SELECT m.id, m.subject, m.memo_type, m.status, m.memo_date, m.employee_id
        FROM memos m
        WHERE m.status NOT IN ('Acknowledged','Closed','Archived')
        ORDER BY m.created_at DESC
        LIMIT 50
        """,
    )
    payroll_warnings = 0
    for run in payroll_ready:
        summary = run.get("validation_summary") or ""
        payroll_warnings += 1 if summary and summary not in {"{}", "[]", "OK", "Passed"} else 0
    counts = {
        "staff_on_duty_today": fetchone(conn, "SELECT COUNT(DISTINCT employee_id) AS c FROM time_logs WHERE work_date=date('now') AND COALESCE(is_absent,0)=0")["c"],
        "attendance_exceptions": len(pending_attendance),
        "ot_pending": len(ot_pending),
        "leave_pending": len(leave_pending),
        "cash_advance_pending": len(cash_advance_pending),
        "payroll_qa_warnings": payroll_warnings,
        "payroll_ready_for_owner_review": len(payroll_ready),
        "annual_reviews_due": len(annual_due),
        "memo_acknowledgments_pending": len(memo_pending),
    }
    payload = {
        "receiver_app": OPERATIONS_APP,
        "privacy_note": "Operations receives status/review context only. Salary/rates, government IDs, detailed payroll, and private HR notes stay in Staff/Payroll.",
        "counts": counts,
        "suggested_operations_actions": [
            "Create Review cards for attendance/OT/leave/cash advance items.",
            "Create Tasks only when a manager chooses to act.",
            "Route final decisions back to Staff/Payroll using the source record IDs; Operations must not compute payroll.",
        ],
    }
    return _event("staff.operations.snapshot", f"ops-snapshot:{now_iso()[:10]}", "Operations Snapshot", now_iso()[:10], payload)


def build_payroll_ready_payload(conn, run_id: int) -> dict[str, Any]:
    run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
    if not run:
        raise ValueError(f"Payroll run {run_id} not found")
    checks = build_payroll_preflight_checks(conn, run["period_start"], run["period_end"])
    payload = {
        "receiver_app": OPERATIONS_APP,
        "run": {
            "id": run["id"],
            "period_start": run["period_start"],
            "period_end": run["period_end"],
            "run_label": run["run_label"],
            "status": run["status"],
            "payout_date": run.get("payout_date"),
            "validation_summary": run.get("validation_summary"),
        },
        "qa": summarize_checks(checks),
        "receiver_instruction": "Show in Operations Review/Home as a management card. Final payroll approval still happens in Staff/Payroll.",
    }
    event = _event("payroll.ready_for_owner_review", f"ops-payroll-ready:{run_id}:{run.get('status')}", "Payroll Run", run_id, payload)
    event.update(payload)
    return event


def build_employee_status_payload(conn, employee_id: int) -> dict[str, Any]:
    emp = fetchone(
        conn,
        """
        SELECT id, employee_code, full_name, department, position, employment_type, status
        FROM employees WHERE id=?
        """,
        (employee_id,),
    )
    if not emp:
        raise ValueError(f"Employee {employee_id} not found")
    payload = {
        "receiver_app": OPERATIONS_APP,
        "employee": {
            "employee_code": emp.get("employee_code"),
            "display_name": emp.get("full_name"),
            "department": emp.get("department"),
            "position": emp.get("position"),
            "role": emp.get("employment_type"),
            "active": emp.get("status") not in {"Inactive", "Separated", "Terminated"},
            "primary_department": emp.get("department"),
            "source_staff_id": emp.get("id"),
        },
        "privacy_note": "Operational identity only. No rates, payroll, government IDs, or private HR notes.",
    }
    event = _event("employee.status.changed", f"ops-employee-status:{employee_id}:{emp.get('status')}", "Employee", employee_id, payload)
    event.update(payload)
    return event


def enqueue_operations_snapshot(conn) -> int:
    payload = build_operations_snapshot_payload(conn)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "Operations Snapshot", None, payload)


def enqueue_payroll_ready_for_operations(conn, run_id: int) -> int:
    payload = build_payroll_ready_payload(conn, run_id)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "Payroll Run", run_id, payload)


def enqueue_employee_status_for_operations(conn, employee_id: int) -> int:
    payload = build_employee_status_payload(conn, employee_id)
    return enqueue_payload(conn, payload["event_type"], payload["external_id"], "Employee", employee_id, payload)
