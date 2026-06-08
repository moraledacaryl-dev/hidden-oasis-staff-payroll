from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from typing import Any

import pandas as pd

from .db import fetchall, fetchone, now_iso


def _bool_int(v: Any, default: int = 0) -> int:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "active", "enabled"):
        return 1
    if s in ("0", "false", "no", "n", "inactive", "disabled"):
        return 0
    return default


def _clean(v: Any, default: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
            return default
        return float(v)
    except Exception:
        return default


def _sheet(df_dict: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    for k, v in df_dict.items():
        if k.strip().lower() == name.strip().lower():
            return v
    return pd.DataFrame()


def create_required_template_xlsx() -> bytes:
    """Return an Excel workbook with all required import templates."""
    sheets: dict[str, pd.DataFrame] = {
        "Employees": pd.DataFrame([
            {
                "employee_code": "EMP-001", "full_name": "Sample Employee", "department": "Reception",
                "position": "Receptionist", "employment_type": "Hourly", "status": "Active",
                "hourly_rate": 75, "daily_rate": 600, "declared_monthly_base": 13000,
                "standard_shift_hours": 9, "unpaid_break_minutes": 60, "security_no_break": 0,
                "benefits_sss": 1, "benefits_philhealth": 1, "benefits_pagibig": 1, "benefits_tax": 0,
                "start_date": "2026-01-01", "regularization_date": "", "supervisor": "",
                "emergency_contact": "", "notes": ""
            }
        ]),
        "Schedules": pd.DataFrame([
            {
                "employee_code": "EMP-001", "work_date": "2026-06-01", "shift_start": "08:00",
                "shift_end": "17:00", "break_minutes": 60, "department": "Reception",
                "location": "Front Desk", "is_rest_day": 0, "notes": ""
            }
        ]),
        "TimeLogs": pd.DataFrame([
            {
                "employee_code": "EMP-001", "work_date": "2026-06-01", "actual_in": "07:58",
                "actual_out": "18:00", "source": "manual/import", "verification_type": "Biometric",
                "approved_ot_hours": 1.0, "ot_status": "Approved", "ot_reason_category": "High guest volume",
                "ot_reason_note": "Front desk rush", "attendance_status": "Reviewed", "notes": ""
            }
        ]),
        "LeaveTypes": pd.DataFrame([
            {"name": "Service Incentive Leave", "default_credits": 5, "paid": 1, "statutory": 1, "requires_approval": 1, "requires_attachment": 0, "annual_reset": 1, "active": 1, "notes": ""}
        ]),
        "LeaveEntitlements": pd.DataFrame([
            {"employee_code": "EMP-001", "leave_type_name": "Service Incentive Leave", "year": 2026, "entitled": 1, "credits": 5, "used": 0}
        ]),
        "LeaveRequests": pd.DataFrame([
            {"employee_code": "EMP-001", "leave_type_name": "Service Incentive Leave", "start_date": "2026-06-05", "end_date": "2026-06-05", "days": 1, "paid": 1, "status": "Approved", "reason": ""}
        ]),
        "CashAdvances": pd.DataFrame([
            {"employee_code": "EMP-001", "request_date": "2026-06-01", "amount": 2000, "release_method": "Cash Drawer", "release_reference": "", "status": "Released", "repayment_per_cutoff": 500, "custom_next_deduction": "", "outstanding_balance": 2000, "approved_by": "Owner", "released_by": "Cashier", "released_at": "2026-06-01", "notes": ""}
        ]),
        "DrawerMovements": pd.DataFrame([
            {"movement_date": "2026-06-01", "drawer_name": "Main Drawer", "movement_type": "Cash Out", "source_type": "Cash Advance", "source_id": "", "amount": 2000, "method": "Cash", "reference": "CA-0001", "description": "Staff cash advance release", "created_by": "Cashier", "status": "For Reconciliation"}
        ]),
        "AppUsers": pd.DataFrame([
            {"display_name": "Caryl / Owner", "role": "Owner", "active": 1}
        ]),
        "FreelanceRates": pd.DataFrame([
            {"name": "Pubmat", "rate": 150, "active": 1, "notes": ""}
        ]),
        "FreelanceOutputs": pd.DataFrame([
            {"employee_code": "EMP-003", "week_start": "2026-06-01", "week_end": "2026-06-07", "output_type_name": "Pubmat", "approved_qty": 8, "rate": 150, "status": "Approved", "notes": ""}
        ]),
        "PayrollAdjustments": pd.DataFrame([
            {"employee_code": "EMP-001", "period_start": "2026-06-01", "period_end": "2026-06-15", "kind": "earning", "label": "Meal Allowance", "amount": 0, "status": "Approved", "notes": ""}
        ]),
        "Holidays": pd.DataFrame([
            {"holiday_date": "2026-06-12", "name": "Independence Day", "holiday_type": "Regular", "active": 1, "notes": ""}
        ]),
        "SSS_Table": pd.DataFrame([
            {"min_comp": 0, "max_comp": 5249.99, "msc": 5000, "ee_share": 250, "er_share": 500, "ec_share": 10, "active": 1}
        ]),
        "BiometricDaily": pd.DataFrame([
            {"employee_code": "EMP-001", "date": "2026-06-01", "time_in": "07:58", "time_out": "17:05", "device_id": "DEVICE-1"}
        ]),
        "BiometricTimestamp": pd.DataFrame([
            {"employee_code": "EMP-001", "timestamp": "2026-06-01 07:58", "punch_type": "IN", "device_id": "DEVICE-1"},
            {"employee_code": "EMP-001", "timestamp": "2026-06-01 17:05", "punch_type": "OUT", "device_id": "DEVICE-1"},
        ]),
        "Instructions": pd.DataFrame([
            {"note": "Fill only the sheets you need. employee_code is the main matching key. Dates should be YYYY-MM-DD and times HH:MM."},
            {"note": "Upload this workbook in Data Import / Templates > Import filled template."},
            {"note": "For old Payroll.zip imports, use the Legacy ZIP importer instead."},
        ]),
    }
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return out.getvalue()


def _employee_id(conn: sqlite3.Connection, employee_code: str) -> int | None:
    row = fetchone(conn, "SELECT id FROM employees WHERE employee_code=?", (employee_code,))
    return int(row["id"]) if row else None


def _leave_type_id(conn: sqlite3.Connection, name: str) -> int | None:
    row = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (name,))
    return int(row["id"]) if row else None


def _freelance_type_id(conn: sqlite3.Connection, name: str) -> int | None:
    row = fetchone(conn, "SELECT id FROM freelance_rate_types WHERE lower(name)=lower(?)", (name,))
    return int(row["id"]) if row else None


def import_template_xlsx(conn: sqlite3.Connection, file_bytes: bytes, file_name: str, actor: str = "Importer") -> dict[str, Any]:
    dfs = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
    counts: dict[str, int] = {}
    errors: list[str] = []
    now = now_iso()

    def inc(name: str, n: int = 1) -> None:
        counts[name] = counts.get(name, 0) + n

    # Employees
    df = _sheet(dfs, "Employees")
    for i, r in df.iterrows():
        try:
            code = _clean(r.get("employee_code"))
            name = _clean(r.get("full_name"))
            if not code or not name:
                continue
            conn.execute(
                """
                INSERT INTO employees(employee_code, full_name, department, position, employment_type, status,
                    hourly_rate, daily_rate, declared_monthly_base, standard_shift_hours, unpaid_break_minutes,
                    security_no_break, benefits_sss, benefits_philhealth, benefits_pagibig, benefits_tax,
                    start_date, regularization_date, supervisor, emergency_contact, notes, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(employee_code) DO UPDATE SET
                    full_name=excluded.full_name, department=excluded.department, position=excluded.position,
                    employment_type=excluded.employment_type, status=excluded.status, hourly_rate=excluded.hourly_rate,
                    daily_rate=excluded.daily_rate, declared_monthly_base=excluded.declared_monthly_base,
                    standard_shift_hours=excluded.standard_shift_hours, unpaid_break_minutes=excluded.unpaid_break_minutes,
                    security_no_break=excluded.security_no_break, benefits_sss=excluded.benefits_sss,
                    benefits_philhealth=excluded.benefits_philhealth, benefits_pagibig=excluded.benefits_pagibig,
                    benefits_tax=excluded.benefits_tax, start_date=excluded.start_date,
                    regularization_date=excluded.regularization_date, supervisor=excluded.supervisor,
                    emergency_contact=excluded.emergency_contact, notes=excluded.notes, updated_at=excluded.updated_at
                """,
                (
                    code, name, _clean(r.get("department"), "General"), _clean(r.get("position")), _clean(r.get("employment_type"), "Hourly"),
                    _clean(r.get("status"), "Active"), _num(r.get("hourly_rate")), _num(r.get("daily_rate")), _num(r.get("declared_monthly_base")),
                    _num(r.get("standard_shift_hours"), 9), int(_num(r.get("unpaid_break_minutes"), 60)), _bool_int(r.get("security_no_break")),
                    _bool_int(r.get("benefits_sss"), 1), _bool_int(r.get("benefits_philhealth"), 1), _bool_int(r.get("benefits_pagibig"), 1),
                    _bool_int(r.get("benefits_tax")), _clean(r.get("start_date")), _clean(r.get("regularization_date")),
                    _clean(r.get("supervisor")), _clean(r.get("emergency_contact")), _clean(r.get("notes")), now, now
                ),
            )
            inc("Employees")
        except Exception as e:
            errors.append(f"Employees row {i+2}: {e}")

    # Departments from employees
    conn.execute("INSERT OR IGNORE INTO departments(name, active) SELECT DISTINCT department, 1 FROM employees WHERE department IS NOT NULL AND department != ''")

    # Holidays
    df = _sheet(dfs, "Holidays")
    for i, r in df.iterrows():
        try:
            hdate = _clean(r.get("holiday_date"))
            hname = _clean(r.get("name"))
            if not hdate or not hname:
                continue
            conn.execute(
                """
                INSERT INTO holidays(holiday_date, name, holiday_type, active, notes, created_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(holiday_date) DO UPDATE SET name=excluded.name, holiday_type=excluded.holiday_type, active=excluded.active, notes=excluded.notes
                """,
                (hdate, hname, _clean(r.get("holiday_type"), "Regular"), _bool_int(r.get("active"), 1), _clean(r.get("notes")), now),
            )
            inc("Holidays")
        except Exception as e:
            errors.append(f"Holidays row {i+2}: {e}")

    # SSS table
    df = _sheet(dfs, "SSS_Table")
    if not df.empty and {"min_comp", "max_comp", "msc", "ee_share", "er_share"}.issubset(set(df.columns)):
        conn.execute("DELETE FROM sss_contribution_table")
        for i, r in df.iterrows():
            try:
                conn.execute(
                    "INSERT INTO sss_contribution_table(min_comp, max_comp, msc, ee_share, er_share, ec_share, active) VALUES(?,?,?,?,?,?,?)",
                    (_num(r.get("min_comp")), _num(r.get("max_comp")), _num(r.get("msc")), _num(r.get("ee_share")), _num(r.get("er_share")), _num(r.get("ec_share")), _bool_int(r.get("active"), 1)),
                )
                inc("SSS_Table")
            except Exception as e:
                errors.append(f"SSS_Table row {i+2}: {e}")

    # Leave types
    df = _sheet(dfs, "LeaveTypes")
    for i, r in df.iterrows():
        try:
            name = _clean(r.get("name"))
            if not name:
                continue
            conn.execute(
                """
                INSERT INTO leave_types(name, default_credits, paid, statutory, requires_approval, requires_attachment, annual_reset, active, notes)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET default_credits=excluded.default_credits, paid=excluded.paid,
                    statutory=excluded.statutory, requires_approval=excluded.requires_approval,
                    requires_attachment=excluded.requires_attachment, annual_reset=excluded.annual_reset,
                    active=excluded.active, notes=excluded.notes
                """,
                (name, _num(r.get("default_credits")), _bool_int(r.get("paid"), 1), _bool_int(r.get("statutory")),
                 _bool_int(r.get("requires_approval"), 1), _bool_int(r.get("requires_attachment")),
                 _bool_int(r.get("annual_reset"), 1), _bool_int(r.get("active"), 1), _clean(r.get("notes"))),
            )
            inc("LeaveTypes")
        except Exception as e:
            errors.append(f"LeaveTypes row {i+2}: {e}")

    # Schedules
    df = _sheet(dfs, "Schedules")
    for i, r in df.iterrows():
        try:
            emp_id = _employee_id(conn, _clean(r.get("employee_code")))
            if not emp_id:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (emp_id, _clean(r.get("work_date")), _clean(r.get("shift_start"), "08:00"), _clean(r.get("shift_end"), "17:00"),
                 int(_num(r.get("break_minutes"), 60)), _clean(r.get("department")), _clean(r.get("location")),
                 _bool_int(r.get("is_rest_day")), _clean(r.get("notes"))),
            )
            inc("Schedules")
        except Exception as e:
            errors.append(f"Schedules row {i+2}: {e}")

    # Time logs
    df = _sheet(dfs, "TimeLogs")
    for i, r in df.iterrows():
        try:
            emp_id = _employee_id(conn, _clean(r.get("employee_code")))
            if not emp_id:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
                    approved_ot_hours, ot_status, ot_reason_category, ot_reason_note, attendance_status, notes, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (emp_id, _clean(r.get("work_date")), _clean(r.get("actual_in")), _clean(r.get("actual_out")),
                 _clean(r.get("source"), "import"), _clean(r.get("verification_type"), "Import"),
                 _num(r.get("approved_ot_hours")), _clean(r.get("ot_status"), "None"),
                 _clean(r.get("ot_reason_category")), _clean(r.get("ot_reason_note")),
                 _clean(r.get("attendance_status"), "Pending"), _clean(r.get("notes")), now, now),
            )
            inc("TimeLogs")
        except Exception as e:
            errors.append(f"TimeLogs row {i+2}: {e}")

    # Entitlements
    df = _sheet(dfs, "LeaveEntitlements")
    for i, r in df.iterrows():
        try:
            emp_id = _employee_id(conn, _clean(r.get("employee_code")))
            lt_id = _leave_type_id(conn, _clean(r.get("leave_type_name")))
            if not emp_id or not lt_id:
                continue
            conn.execute(
                """
                INSERT INTO employee_leave_entitlements(employee_id, leave_type_id, year, entitled, credits, used)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(employee_id, leave_type_id, year) DO UPDATE SET entitled=excluded.entitled, credits=excluded.credits, used=excluded.used
                """,
                (emp_id, lt_id, int(_num(r.get("year"), datetime.now().year)), _bool_int(r.get("entitled"), 1), _num(r.get("credits")), _num(r.get("used"))),
            )
            inc("LeaveEntitlements")
        except Exception as e:
            errors.append(f"LeaveEntitlements row {i+2}: {e}")

    # Leave requests
    df = _sheet(dfs, "LeaveRequests")
    for i, r in df.iterrows():
        try:
            emp_id = _employee_id(conn, _clean(r.get("employee_code")))
            lt_id = _leave_type_id(conn, _clean(r.get("leave_type_name")))
            if not emp_id or not lt_id:
                continue
            conn.execute(
                "INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (emp_id, lt_id, _clean(r.get("start_date")), _clean(r.get("end_date")), _num(r.get("days")), _bool_int(r.get("paid"), 1), _clean(r.get("status"), "Pending"), _clean(r.get("reason")), now),
            )
            inc("LeaveRequests")
        except Exception as e:
            errors.append(f"LeaveRequests row {i+2}: {e}")

    # Cash advances
    df = _sheet(dfs, "CashAdvances")
    for i, r in df.iterrows():
        try:
            emp_id = _employee_id(conn, _clean(r.get("employee_code")))
            if not emp_id:
                continue
            amount = _num(r.get("amount"))
            outstanding = _num(r.get("outstanding_balance"), amount)
            conn.execute(
                """
                INSERT INTO cash_advances(employee_id, request_date, amount, release_method, release_reference, status,
                    repayment_per_cutoff, custom_next_deduction, outstanding_balance, approved_by, released_by, released_at, notes, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (emp_id, _clean(r.get("request_date")), amount, _clean(r.get("release_method"), "Cash Drawer"),
                 _clean(r.get("release_reference")), _clean(r.get("status"), "Released"), _num(r.get("repayment_per_cutoff")),
                 None if _clean(r.get("custom_next_deduction")) == "" else _num(r.get("custom_next_deduction")),
                 outstanding, _clean(r.get("approved_by")), _clean(r.get("released_by")), _clean(r.get("released_at")), _clean(r.get("notes")), now),
            )
            inc("CashAdvances")
        except Exception as e:
            errors.append(f"CashAdvances row {i+2}: {e}")

    # App users
    df = _sheet(dfs, "AppUsers")
    for i, r in df.iterrows():
        try:
            display_name = _clean(r.get("display_name"))
            if not display_name:
                continue
            conn.execute(
                "INSERT INTO app_users(display_name, role, active, created_at) VALUES(?,?,?,?) ON CONFLICT(display_name) DO UPDATE SET role=excluded.role, active=excluded.active",
                (display_name, _clean(r.get("role"), "Viewer"), _bool_int(r.get("active"), 1), now),
            )
            inc("AppUsers")
        except Exception as e:
            errors.append(f"AppUsers row {i+2}: {e}")

    # Drawer movements
    df = _sheet(dfs, "DrawerMovements")
    for i, r in df.iterrows():
        try:
            if not _clean(r.get("movement_date")) or _num(r.get("amount")) <= 0:
                continue
            conn.execute(
                """
                INSERT INTO cash_drawer_movements(movement_date, drawer_name, movement_type, source_type, source_id, amount, method, reference, description, created_by, status, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (_clean(r.get("movement_date")), _clean(r.get("drawer_name"), "Main Drawer"), _clean(r.get("movement_type"), "Cash Out"), _clean(r.get("source_type"), "Manual"), None if _clean(r.get("source_id"))=="" else int(_num(r.get("source_id"))), _num(r.get("amount")), _clean(r.get("method"), "Cash"), _clean(r.get("reference")), _clean(r.get("description")), _clean(r.get("created_by"), actor), _clean(r.get("status"), "For Reconciliation"), now),
            )
            inc("DrawerMovements")
        except Exception as e:
            errors.append(f"DrawerMovements row {i+2}: {e}")

    # Freelance rates
    df = _sheet(dfs, "FreelanceRates")
    for i, r in df.iterrows():
        try:
            name = _clean(r.get("name"))
            if not name:
                continue
            conn.execute(
                "INSERT INTO freelance_rate_types(name, rate, active, notes) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET rate=excluded.rate, active=excluded.active, notes=excluded.notes",
                (name, _num(r.get("rate")), _bool_int(r.get("active"), 1), _clean(r.get("notes"))),
            )
            inc("FreelanceRates")
        except Exception as e:
            errors.append(f"FreelanceRates row {i+2}: {e}")

    # Freelance outputs
    df = _sheet(dfs, "FreelanceOutputs")
    for i, r in df.iterrows():
        try:
            emp_id = _employee_id(conn, _clean(r.get("employee_code")))
            ft_id = _freelance_type_id(conn, _clean(r.get("output_type_name")))
            if not emp_id or not ft_id:
                continue
            conn.execute(
                "INSERT INTO freelance_outputs(employee_id, week_start, week_end, output_type_id, approved_qty, rate, status, notes, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (emp_id, _clean(r.get("week_start")), _clean(r.get("week_end")), ft_id, _num(r.get("approved_qty")), _num(r.get("rate")), _clean(r.get("status"), "Approved"), _clean(r.get("notes")), now),
            )
            inc("FreelanceOutputs")
        except Exception as e:
            errors.append(f"FreelanceOutputs row {i+2}: {e}")

    # Payroll adjustments
    df = _sheet(dfs, "PayrollAdjustments")
    for i, r in df.iterrows():
        try:
            emp_id = _employee_id(conn, _clean(r.get("employee_code")))
            if not emp_id:
                continue
            conn.execute(
                "INSERT INTO payroll_adjustments(employee_id, period_start, period_end, kind, label, amount, status, notes, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (emp_id, _clean(r.get("period_start")), _clean(r.get("period_end")), _clean(r.get("kind"), "earning"), _clean(r.get("label")), _num(r.get("amount")), _clean(r.get("status"), "Approved"), _clean(r.get("notes")), now),
            )
            inc("PayrollAdjustments")
        except Exception as e:
            errors.append(f"PayrollAdjustments row {i+2}: {e}")

    total = sum(counts.values())
    conn.execute(
        "INSERT INTO data_import_batches(file_name, import_type, imported_at, imported_by, row_count, success_count, error_count, notes) VALUES(?,?,?,?,?,?,?,?)",
        (file_name, "Template Excel", now, actor, total + len(errors), total, len(errors), "\n".join(errors[:50])),
    )
    conn.execute("INSERT INTO audit_logs(actor, action, table_name, details, created_at) VALUES(?,?,?,?,?)", (actor, "Imported template workbook", "data_import_batches", json.dumps(counts), now))
    conn.commit()
    return {"counts": counts, "errors": errors}


def import_legacy_payroll_zip(conn: sqlite3.Connection, file_bytes: bytes, file_name: str, actor: str = "Legacy Importer") -> dict[str, Any]:
    """Import the older uploaded Payroll.zip or any zip containing payroll.sqlite.

    This is intentionally migration-oriented, not a perfect clone. It imports data into the new model
    while preserving the original payroll history, schedules, time logs, SSS table, and 13th-month records.
    """
    counts: dict[str, int] = {}
    errors: list[str] = []
    now = now_iso()

    def inc(name: str, n: int = 1) -> None:
        counts[name] = counts.get(name, 0) + n

    with tempfile.TemporaryDirectory() as td:
        zpath = os.path.join(td, "upload.zip")
        with open(zpath, "wb") as f:
            f.write(file_bytes)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(td)
        sqlite_candidates: list[str] = []
        xlsx_candidates: list[str] = []
        for root, _, files in os.walk(td):
            # avoid virtualenv sludge
            if ".venv" in root.split(os.sep):
                continue
            for fn in files:
                lower = fn.lower()
                path = os.path.join(root, fn)
                if lower.endswith((".sqlite", ".db")):
                    sqlite_candidates.append(path)
                elif lower.endswith((".xlsx", ".xls")):
                    xlsx_candidates.append(path)
        if not sqlite_candidates and xlsx_candidates:
            # Import first workbook if it is a template zip.
            with open(xlsx_candidates[0], "rb") as f:
                return import_template_xlsx(conn, f.read(), os.path.basename(xlsx_candidates[0]), actor)

        if not sqlite_candidates:
            return {"counts": {}, "errors": ["No .sqlite/.db or template workbook was found inside the zip."]}

        old_path = sqlite_candidates[0]
        old = sqlite3.connect(old_path)
        old.row_factory = sqlite3.Row
        old_tables = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        def old_rows(table: str) -> list[dict[str, Any]]:
            if table not in old_tables:
                return []
            return [dict(r) for r in old.execute(f"SELECT * FROM {table}").fetchall()]

        # Positions lookup
        pos = {}
        if "positions" in old_tables:
            pos = {r["id"]: r.get("name") for r in old_rows("positions")}

        old_to_new_emp: dict[int, int] = {}
        for r in old_rows("employees"):
            try:
                old_id = int(r["id"])
                code = f"OLD-{old_id:03d}"
                full_name = _clean(r.get("fullname"), f"Legacy Employee {old_id}")
                position = pos.get(r.get("primary_position_id")) or ""
                with_benefits = _bool_int(r.get("with_benefits"), 1)
                status = "Active" if _bool_int(r.get("is_active"), 1) else "Inactive"
                emp_type = _clean(r.get("employment_type"), "Hourly").replace("full_time", "Hourly").replace("part_time", "Hourly").replace("on_call", "On-call")
                conn.execute(
                    """
                    INSERT INTO employees(employee_code, full_name, department, position, employment_type, status,
                        hourly_rate, daily_rate, declared_monthly_base, standard_shift_hours, unpaid_break_minutes,
                        security_no_break, benefits_sss, benefits_philhealth, benefits_pagibig, benefits_tax,
                        start_date, notes, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(employee_code) DO UPDATE SET full_name=excluded.full_name, position=excluded.position,
                        employment_type=excluded.employment_type, status=excluded.status, hourly_rate=excluded.hourly_rate,
                        daily_rate=excluded.daily_rate, declared_monthly_base=excluded.declared_monthly_base,
                        benefits_sss=excluded.benefits_sss, benefits_philhealth=excluded.benefits_philhealth,
                        benefits_pagibig=excluded.benefits_pagibig, updated_at=excluded.updated_at
                    """,
                    (
                        code, full_name, "Legacy Import", position, emp_type, status,
                        _num(r.get("hourly_base") or r.get("display_rate_value")), _num(r.get("display_rate_value")),
                        _num(r.get("monthly_base")), 9, 60, 1 if "security" in position.lower() else 0,
                        _bool_int(r.get("apply_sss"), with_benefits), _bool_int(r.get("apply_ph"), with_benefits),
                        _bool_int(r.get("apply_pi"), with_benefits), 0, _clean(r.get("date_started")),
                        "Imported from legacy Payroll.zip", now, now
                    ),
                )
                new_id = _employee_id(conn, code)
                old_to_new_emp[old_id] = int(new_id)
                inc("Legacy employees")
            except Exception as e:
                errors.append(f"Legacy employees id {r.get('id')}: {e}")

        conn.execute("INSERT OR IGNORE INTO departments(name, active) VALUES('Legacy Import',1)")

        # SSS table
        if "sss_contribution_table" in old_tables:
            conn.execute("DELETE FROM sss_contribution_table")
            for r in old_rows("sss_contribution_table"):
                try:
                    conn.execute(
                        "INSERT INTO sss_contribution_table(min_comp, max_comp, msc, ee_share, er_share, ec_share, active) VALUES(?,?,?,?,?,?,1)",
                        (_num(r.get("range_min")), _num(r.get("range_max")), _num(r.get("msc")), _num(r.get("ee_share")), _num(r.get("er_share")), _num(r.get("ec_share"))),
                    )
                    inc("Legacy SSS rows")
                except Exception as e:
                    errors.append(f"Legacy SSS row: {e}")

        # Holidays
        for r in old_rows("holidays"):
            try:
                hdate = _clean(r.get("holi_date"))
                if not hdate:
                    continue
                conn.execute(
                    """
                    INSERT INTO holidays(holiday_date, name, holiday_type, active, notes, created_at)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(holiday_date) DO UPDATE SET name=excluded.name, holiday_type=excluded.holiday_type, active=excluded.active, notes=excluded.notes
                    """,
                    (hdate, _clean(r.get("name"), "Legacy Holiday"), _clean(r.get("holi_type"), "Regular").title(), 1, "Imported from legacy Payroll.zip", now),
                )
                inc("Legacy holidays")
            except Exception as e:
                errors.append(f"Legacy holidays row: {e}")

        # Daily shifts/schedules
        for r in old_rows("daily_shifts"):
            try:
                emp_id = old_to_new_emp.get(int(r["emp_id"]))
                if not emp_id:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (emp_id, _clean(r.get("work_date")), _clean(r.get("scheduled_start")), _clean(r.get("scheduled_end")),
                     int(_num(r.get("scheduled_break_mins"), 60)), "Legacy Import", "", _bool_int(r.get("is_restday")),
                     _clean(r.get("notes"))),
                )
                inc("Legacy schedules")
            except Exception as e:
                errors.append(f"Legacy daily_shifts id {r.get('id')}: {e}")

        # Time logs
        for r in old_rows("time_logs"):
            try:
                emp_id = old_to_new_emp.get(int(r["emp_id"]))
                if not emp_id:
                    continue
                ot = _num(r.get("ot_approved_hours"))
                conn.execute(
                    """
                    INSERT OR REPLACE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
                        is_absent, absence_type, offset_allowed, detected_ot_hours, approved_ot_hours, ot_status,
                        attendance_status, notes, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (emp_id, _clean(r.get("work_date")), _clean(r.get("actual_in")), _clean(r.get("actual_out")),
                     "legacy_import", "Legacy", _bool_int(r.get("is_absent")), "", _bool_int(r.get("offset_allowed")),
                     _num(r.get("overstay_mins")) / 60.0, ot, "Approved" if ot > 0 else "None", "Reviewed", _clean(r.get("remarks")), now, now),
                )
                inc("Legacy time logs")
            except Exception as e:
                errors.append(f"Legacy time_logs id {r.get('id')}: {e}")

        # Other earnings/deductions
        for table, kind in [("payroll_other_earnings", "earning"), ("payroll_other_deductions", "deduction")]:
            for r in old_rows(table):
                try:
                    emp_id = old_to_new_emp.get(int(r["emp_id"]))
                    if not emp_id:
                        continue
                    conn.execute(
                        "INSERT INTO payroll_adjustments(employee_id, period_start, period_end, kind, label, amount, status, notes, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (emp_id, _clean(r.get("period_start")), _clean(r.get("period_end")), kind, _clean(r.get("item")), _num(r.get("amount")), "Approved", _clean(r.get("notes")), now),
                    )
                    inc(f"Legacy {kind} adjustments")
                except Exception as e:
                    errors.append(f"Legacy {table} id {r.get('id')}: {e}")

        # Payroll history -> payroll runs/items
        run_key_to_id: dict[tuple[str, str, str], int] = {}
        old_ph_to_new_item: dict[int, int] = {}
        for r in old_rows("payroll_history"):
            try:
                emp_id = old_to_new_emp.get(int(r["emp_id"]))
                if not emp_id:
                    continue
                ps = _clean(r.get("period_start"))
                pe = _clean(r.get("period_end"))
                label = _clean(r.get("period_label"), "Legacy Payroll")
                key = (ps, pe, label)
                if key not in run_key_to_id:
                    conn.execute(
                        """
                        INSERT INTO payroll_runs(period_start, period_end, payout_date, run_label, status, prepared_by, created_at)
                        VALUES(?,?,?,?,?,?,?)
                        ON CONFLICT(period_start, period_end, run_label) DO UPDATE SET status=excluded.status
                        """,
                        (ps, pe, pe, label, "Locked", "Legacy Import", now),
                    )
                    run_id = fetchone(conn, "SELECT id FROM payroll_runs WHERE period_start=? AND period_end=? AND run_label=?", key)["id"]
                    run_key_to_id[key] = int(run_id)
                    inc("Legacy payroll runs")
                run_id = run_key_to_id[key]
                gross = _num(r.get("gross"))
                net = _num(r.get("net"))
                deductions = _num(r.get("sss_ee")) + _num(r.get("ph_ee")) + _num(r.get("pi_ee")) + _num(r.get("other_ded")) + max(0.0, gross - net - (_num(r.get("sss_ee")) + _num(r.get("ph_ee")) + _num(r.get("pi_ee")) + _num(r.get("other_ded"))))
                conn.execute(
                    """
                    INSERT INTO payroll_items(payroll_run_id, employee_id, regular_hours, regular_pay,
                        approved_ot_hours, ot_pay, night_diff_hours, night_diff_pay, holiday_pay, gross_pay,
                        sss_ee, philhealth_ee, pagibig_ee, other_deductions, total_deductions, net_pay, warnings, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(payroll_run_id, employee_id) DO UPDATE SET
                        regular_hours=excluded.regular_hours,
                        regular_pay=excluded.regular_pay,
                        approved_ot_hours=excluded.approved_ot_hours,
                        ot_pay=excluded.ot_pay,
                        night_diff_pay=excluded.night_diff_pay,
                        holiday_pay=excluded.holiday_pay,
                        gross_pay=excluded.gross_pay,
                        sss_ee=excluded.sss_ee,
                        philhealth_ee=excluded.philhealth_ee,
                        pagibig_ee=excluded.pagibig_ee,
                        other_deductions=excluded.other_deductions,
                        total_deductions=excluded.total_deductions,
                        net_pay=excluded.net_pay,
                        warnings=excluded.warnings
                    """,
                    (run_id, emp_id, _num(r.get("hours_paid")), _num(r.get("basic")), _num(r.get("ot_hours")), _num(r.get("ot")),
                     0, _num(r.get("nd")), _num(r.get("holiday")), gross, _num(r.get("sss_ee")), _num(r.get("ph_ee")), _num(r.get("pi_ee")),
                     _num(r.get("other_ded")), round(max(0.0, gross - net), 2), net, "Imported locked legacy payroll item", now),
                )
                item = fetchone(conn, "SELECT id FROM payroll_items WHERE payroll_run_id=? AND employee_id=?", (run_id, emp_id))
                if item:
                    old_ph_to_new_item[int(r["id"])] = int(item["id"])
                inc("Legacy payroll items")
            except Exception as e:
                errors.append(f"Legacy payroll_history id {r.get('id')}: {e}")

        for r in old_rows("payroll_history_lines"):
            try:
                item_id = old_ph_to_new_item.get(int(r["payroll_history_id"]))
                if not item_id:
                    continue
                conn.execute(
                    "INSERT INTO payroll_item_lines(payroll_item_id, kind, label, amount, sort_order, notes) VALUES(?,?,?,?,?,?)",
                    (item_id, _clean(r.get("kind"), "earning"), _clean(r.get("label")), _num(r.get("amount")), int(_num(r.get("sort_order"))), "Imported from legacy payroll history lines"),
                )
                inc("Legacy payroll lines")
            except Exception as e:
                errors.append(f"Legacy payroll_history_lines id {r.get('id')}: {e}")

        # 13th month runs
        for r in old_rows("thirteenth_month_runs"):
            try:
                emp_id = old_to_new_emp.get(int(r["emp_id"]))
                if not emp_id:
                    continue
                year = int(_num(r.get("year"), datetime.now().year))
                gross = _num(r.get("gross"))
                net = _num(r.get("net"), gross)
                period_label = _clean(r.get("period_label"), f"13th Month Pay - {year}")
                conn.execute(
                    """
                    INSERT INTO payroll_13th_month_runs(employee_id, year, period_label, basis_amount, base_13th_amount,
                        adjustment_amount, deductions, net_13th_pay, status, release_date, prepared_by, notes, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(employee_id, year, period_label) DO UPDATE SET net_13th_pay=excluded.net_13th_pay, updated_at=excluded.updated_at
                    """,
                    (emp_id, year, period_label, gross * 12, gross, 0, max(0.0, gross - net), net, "Locked", _clean(r.get("release_date")), "Legacy Import", "Imported from legacy Payroll.zip", now, now),
                )
                inc("Legacy 13th month")
            except Exception as e:
                errors.append(f"Legacy thirteenth_month_runs id {r.get('id')}: {e}")

    total = sum(counts.values())
    conn.execute(
        "INSERT INTO data_import_batches(file_name, import_type, imported_at, imported_by, row_count, success_count, error_count, notes) VALUES(?,?,?,?,?,?,?,?)",
        (file_name, "Legacy Payroll ZIP/SQLite", now, actor, total + len(errors), total, len(errors), "\n".join(errors[:100])),
    )
    conn.execute("INSERT INTO audit_logs(actor, action, table_name, details, created_at) VALUES(?,?,?,?,?)", (actor, "Imported legacy Payroll zip/sqlite", "data_import_batches", json.dumps(counts), now))
    conn.commit()
    return {"counts": counts, "errors": errors}


def export_table_to_excel(conn: sqlite3.Connection, table_name: str) -> bytes:
    safe = table_name.replace(";", "").replace("--", "")
    df = pd.read_sql_query(f"SELECT * FROM {safe}", conn)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=safe[:31])
    return out.getvalue()


def export_full_database_snapshot_xlsx(conn: sqlite3.Connection) -> bytes:
    tables = [
        "employees", "schedules", "time_logs", "leave_types", "employee_leave_entitlements",
        "leave_requests", "cash_advances", "cash_advance_repayments", "freelance_rate_types",
        "freelance_outputs", "payroll_runs", "payroll_items", "payroll_item_lines",
        "payroll_adjustments", "payroll_13th_month_runs", "payroll_13th_month_lines",
        "infractions", "memos", "staff_requests", "annual_reviews", "holidays",
        "sss_contribution_table", "accounting_export_queue", "cash_drawer_movements", "app_users", "audit_logs"
    ]
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for t in tables:
            try:
                pd.read_sql_query(f"SELECT * FROM {t}", conn).to_excel(writer, index=False, sheet_name=t[:31])
            except Exception:
                pass
    return out.getvalue()
