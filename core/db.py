from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Iterable

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
DB_PATH = Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DATA_DIR / "staff_payroll.sqlite"))).expanduser()


def get_conn(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timeout_seconds = max(1.0, float(os.getenv("STAFF_PAYROLL_DB_TIMEOUT_SECONDS", "15")))
    conn = sqlite3.connect(str(db_path), timeout=timeout_seconds, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def fetchall(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def fetchone(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None



def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Add a column if an older local database was created before the column existed."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migration_1_existing_columns(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "payroll_items", "sss_er", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "payroll_items", "sss_ec", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "payroll_items", "philhealth_er", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "payroll_items", "pagibig_er", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "annual_reviews", "auto_summary", "TEXT")
    ensure_column(conn, "payroll_runs", "validation_summary", "TEXT")
    ensure_column(conn, "cash_advances", "drawer_movement_id", "INTEGER")
    ensure_column(conn, "time_logs", "reference_occupancy", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "time_logs", "reference_guest_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "time_logs", "reference_order_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "time_logs", "reference_sales", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "time_logs", "reference_event_flag", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "app_users", "password_hash", "TEXT")
    ensure_column(conn, "app_users", "must_change_password", "INTEGER NOT NULL DEFAULT 1")
    ensure_column(conn, "app_users", "last_login_at", "TEXT")
    ensure_column(conn, "app_users", "employee_id", "INTEGER")
    ensure_column(conn, "scheduled_shifts", "legacy_schedule_id", "INTEGER")
    ensure_column(conn, "scheduled_shifts", "source", "TEXT NOT NULL DEFAULT 'planned'")
    ensure_column(conn, "payroll_corrections", "status", "TEXT NOT NULL DEFAULT 'Recorded'")
    ensure_column(conn, "payroll_corrections", "applied_to_run_id", "INTEGER")
    ensure_column(conn, "payroll_corrections", "applied_at", "TEXT")
    ensure_column(conn, "payroll_corrections", "voided_by", "TEXT")
    ensure_column(conn, "payroll_corrections", "void_reason", "TEXT")
    ensure_column(conn, "payroll_corrections", "voided_at", "TEXT")


def _migration_2_account_security(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "app_users", "session_version", "INTEGER NOT NULL DEFAULT 1")
    ensure_column(conn, "app_users", "mfa_secret", "TEXT")
    ensure_column(conn, "app_users", "mfa_enabled", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "app_users", "mfa_confirmed_at", "TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            identifier TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            failed_count INTEGER NOT NULL DEFAULT 0,
            last_failed_at TEXT,
            locked_until TEXT,
            PRIMARY KEY(identifier, ip_address)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_attempts_locked_until ON login_attempts(locked_until)"
    )


def _migration_3_general_manager_label(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE app_users SET role='General Manager' WHERE lower(role) IN ('supervisor','manager','department head')"
    )


def _migration_4_staff_requestable_leave_types(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "leave_types", "staff_requestable", "INTEGER NOT NULL DEFAULT 1")
    conn.execute(
        "UPDATE leave_types SET staff_requestable=0 WHERE lower(name) IN ('awol','suspension')"
    )


def _migration_5_employee_schedule_defaults(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "employees", "default_shift_start", "TEXT")
    ensure_column(conn, "employees", "default_shift_end", "TEXT")


def _migration_6_attendance_import_triage(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "time_logs", "review_reason", "TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_day_markers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,
            marker_type TEXT NOT NULL,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(employee_id, work_date, marker_type)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_day_markers_week ON schedule_day_markers(work_date, marker_type, active)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_time_logs_review_status ON time_logs(attendance_status, work_date)"
    )


MIGRATIONS: tuple[tuple[int, str, Callable[[sqlite3.Connection], None]], ...] = (
    (1, "existing incremental columns", _migration_1_existing_columns),
    (2, "account security and login throttling", _migration_2_account_security),
    (3, "general manager role label", _migration_3_general_manager_label),
    (4, "staff-requestable leave types", _migration_4_staff_requestable_leave_types),
    (5, "employee schedule defaults", _migration_5_employee_schedule_defaults),
    (6, "attendance import triage", _migration_6_attendance_import_triage),
)


def run_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {
        int(row[0])
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, name, migration in MIGRATIONS:
        if version in applied:
            continue
        migration(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?,?,?)",
            (version, name, now_iso()),
        )
        conn.commit()

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            department TEXT NOT NULL DEFAULT 'General',
            position TEXT NOT NULL DEFAULT '',
            employment_type TEXT NOT NULL DEFAULT 'Hourly',
            status TEXT NOT NULL DEFAULT 'Active',
            hourly_rate REAL NOT NULL DEFAULT 0,
            daily_rate REAL NOT NULL DEFAULT 0,
            declared_monthly_base REAL NOT NULL DEFAULT 0,
            standard_shift_hours REAL NOT NULL DEFAULT 9,
            unpaid_break_minutes INTEGER NOT NULL DEFAULT 60,
            security_no_break INTEGER NOT NULL DEFAULT 0,
            benefits_sss INTEGER NOT NULL DEFAULT 1,
            benefits_philhealth INTEGER NOT NULL DEFAULT 1,
            benefits_pagibig INTEGER NOT NULL DEFAULT 1,
            benefits_tax INTEGER NOT NULL DEFAULT 0,
            start_date TEXT,
            regularization_date TEXT,
            supervisor TEXT,
            emergency_contact TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS employee_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            old_status TEXT,
            new_status TEXT NOT NULL,
            reason TEXT,
            effective_date TEXT NOT NULL,
            changed_by TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            work_date TEXT NOT NULL,
            shift_start TEXT NOT NULL,
            shift_end TEXT NOT NULL,
            break_minutes INTEGER NOT NULL DEFAULT 60,
            department TEXT,
            location TEXT,
            is_rest_day INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            UNIQUE(employee_id, work_date, shift_start)
        );

        CREATE TABLE IF NOT EXISTS scheduled_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            position TEXT NOT NULL DEFAULT 'Other',
            department TEXT,
            break_minutes INTEGER NOT NULL DEFAULT 60,
            status TEXT NOT NULL DEFAULT 'Draft',
            notes TEXT,
            legacy_schedule_id INTEGER,
            source TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS biometric_import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            imported_by TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS data_import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            import_type TEXT NOT NULL DEFAULT 'Template/ZIP',
            imported_at TEXT NOT NULL,
            imported_by TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS app_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'Owner',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cash_drawer_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_date TEXT NOT NULL,
            drawer_name TEXT NOT NULL DEFAULT 'Main Drawer',
            movement_type TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id INTEGER,
            amount REAL NOT NULL,
            method TEXT NOT NULL DEFAULT 'Cash',
            reference TEXT,
            description TEXT,
            created_by TEXT,
            status TEXT NOT NULL DEFAULT 'For Reconciliation',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS time_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            work_date TEXT NOT NULL,
            actual_in TEXT,
            actual_out TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            verification_type TEXT DEFAULT 'Manual',
            biometric_batch_id INTEGER REFERENCES biometric_import_batches(id) ON DELETE SET NULL,
            device_employee_code TEXT,
            device_id TEXT,
            is_absent INTEGER NOT NULL DEFAULT 0,
            absence_type TEXT,
            offset_allowed INTEGER NOT NULL DEFAULT 0,
            detected_ot_hours REAL NOT NULL DEFAULT 0,
            approved_ot_hours REAL NOT NULL DEFAULT 0,
            ot_status TEXT NOT NULL DEFAULT 'None',
            ot_reason_category TEXT,
            ot_reason_note TEXT,
            reference_occupancy REAL NOT NULL DEFAULT 0,
            reference_guest_count INTEGER NOT NULL DEFAULT 0,
            reference_order_count INTEGER NOT NULL DEFAULT 0,
            reference_sales REAL NOT NULL DEFAULT 0,
            reference_event_flag INTEGER NOT NULL DEFAULT 0,
            reviewed_by TEXT,
            reviewed_at TEXT,
            attendance_status TEXT NOT NULL DEFAULT 'Pending',
            review_reason TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(employee_id, work_date, actual_in, actual_out, source)
        );

        CREATE TABLE IF NOT EXISTS attendance_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_log_id INTEGER NOT NULL REFERENCES time_logs(id) ON DELETE CASCADE,
            reviewer TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT,
            approved_ot_hours REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS leave_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_credits REAL NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 1,
            statutory INTEGER NOT NULL DEFAULT 0,
            requires_approval INTEGER NOT NULL DEFAULT 1,
            requires_attachment INTEGER NOT NULL DEFAULT 0,
            annual_reset INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS employee_leave_entitlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            leave_type_id INTEGER NOT NULL REFERENCES leave_types(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            entitled INTEGER NOT NULL DEFAULT 0,
            credits REAL NOT NULL DEFAULT 0,
            used REAL NOT NULL DEFAULT 0,
            UNIQUE(employee_id, leave_type_id, year)
        );

        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            leave_type_id INTEGER NOT NULL REFERENCES leave_types(id),
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            days REAL NOT NULL,
            paid INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Pending',
            reason TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            payroll_applied INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cash_advances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            request_date TEXT NOT NULL,
            amount REAL NOT NULL,
            release_method TEXT NOT NULL DEFAULT 'Cash Drawer',
            release_reference TEXT,
            status TEXT NOT NULL DEFAULT 'Approved',
            repayment_per_cutoff REAL NOT NULL DEFAULT 0,
            custom_next_deduction REAL,
            outstanding_balance REAL NOT NULL,
            drawer_movement_id INTEGER,
            approved_by TEXT,
            released_by TEXT,
            released_at TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cash_advance_repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cash_advance_id INTEGER NOT NULL REFERENCES cash_advances(id) ON DELETE CASCADE,
            payroll_run_id INTEGER,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            method TEXT NOT NULL DEFAULT 'Payroll Deduction',
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS freelance_rate_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            rate REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS freelance_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            output_type_id INTEGER NOT NULL REFERENCES freelance_rate_types(id),
            approved_qty REAL NOT NULL DEFAULT 0,
            rate REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Approved',
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payroll_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            payout_date TEXT NOT NULL,
            run_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Draft',
            prepared_by TEXT,
            approved_by TEXT,
            approved_at TEXT,
            paid_at TEXT,
            locked_at TEXT,
            reopen_reason TEXT,
            validation_summary TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(period_start, period_end, run_label)
        );

        CREATE TABLE IF NOT EXISTS payroll_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            adjustment_type TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            apply_to_next_run INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Recorded',
            applied_to_run_id INTEGER,
            applied_at TEXT,
            voided_by TEXT,
            void_reason TEXT,
            voided_at TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payroll_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            regular_hours REAL NOT NULL DEFAULT 0,
            regular_pay REAL NOT NULL DEFAULT 0,
            approved_ot_hours REAL NOT NULL DEFAULT 0,
            ot_pay REAL NOT NULL DEFAULT 0,
            night_diff_hours REAL NOT NULL DEFAULT 0,
            night_diff_pay REAL NOT NULL DEFAULT 0,
            holiday_pay REAL NOT NULL DEFAULT 0,
            paid_leave_days REAL NOT NULL DEFAULT 0,
            paid_leave_pay REAL NOT NULL DEFAULT 0,
            freelance_pay REAL NOT NULL DEFAULT 0,
            other_earnings REAL NOT NULL DEFAULT 0,
            gross_pay REAL NOT NULL DEFAULT 0,
            late_minutes REAL NOT NULL DEFAULT 0,
            undertime_minutes REAL NOT NULL DEFAULT 0,
            unpaid_absence_days REAL NOT NULL DEFAULT 0,
            sss_ee REAL NOT NULL DEFAULT 0,
            philhealth_ee REAL NOT NULL DEFAULT 0,
            pagibig_ee REAL NOT NULL DEFAULT 0,
            sss_er REAL NOT NULL DEFAULT 0,
            sss_ec REAL NOT NULL DEFAULT 0,
            philhealth_er REAL NOT NULL DEFAULT 0,
            pagibig_er REAL NOT NULL DEFAULT 0,
            tax REAL NOT NULL DEFAULT 0,
            cash_advance_deduction REAL NOT NULL DEFAULT 0,
            other_deductions REAL NOT NULL DEFAULT 0,
            total_deductions REAL NOT NULL DEFAULT 0,
            net_pay REAL NOT NULL DEFAULT 0,
            warnings TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(payroll_run_id, employee_id)
        );

        CREATE TABLE IF NOT EXISTS payroll_item_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_item_id INTEGER NOT NULL REFERENCES payroll_items(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            hours REAL,
            days REAL,
            quantity REAL,
            notes TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sss_contribution_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            min_comp REAL NOT NULL,
            max_comp REAL NOT NULL,
            msc REAL NOT NULL,
            ee_share REAL NOT NULL,
            er_share REAL NOT NULL,
            ec_share REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(min_comp, max_comp)
        );

        CREATE TABLE IF NOT EXISTS infractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            incident_date TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'Note',
            description TEXT NOT NULL,
            linked_time_log_id INTEGER REFERENCES time_logs(id) ON DELETE SET NULL,
            action_taken TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            created_by TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            memo_date TEXT NOT NULL,
            memo_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Draft',
            acknowledged_at TEXT,
            issued_by TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS staff_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            request_date TEXT NOT NULL,
            request_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            details TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            reviewed_by TEXT,
            reviewed_at TEXT,
            decision_notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS annual_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            review_period_start TEXT NOT NULL,
            review_period_end TEXT NOT NULL,
            reliability_score INTEGER,
            punctuality_score INTEGER,
            guest_service_score INTEGER,
            teamwork_score INTEGER,
            policy_score INTEGER,
            strengths TEXT,
            improvement_points TEXT,
            auto_summary TEXT,
            recommendation TEXT,
            status TEXT NOT NULL DEFAULT 'Draft',
            reviewer TEXT,
            created_at TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS biometric_import_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT NOT NULL UNIQUE,
            import_mode TEXT NOT NULL DEFAULT 'Timestamp Rows',
            employee_code_column TEXT,
            date_column TEXT,
            time_in_column TEXT,
            time_out_column TEXT,
            timestamp_column TEXT,
            punch_type_column TEXT,
            device_id_column TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payroll_13th_month_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            period_label TEXT NOT NULL,
            basis_amount REAL NOT NULL DEFAULT 0,
            base_13th_amount REAL NOT NULL DEFAULT 0,
            adjustment_amount REAL NOT NULL DEFAULT 0,
            deductions REAL NOT NULL DEFAULT 0,
            net_13th_pay REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Draft',
            release_date TEXT,
            prepared_by TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(employee_id, year, period_label)
        );

        CREATE TABLE IF NOT EXISTS payroll_13th_month_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES payroll_13th_month_runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            notes TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0
        );


        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            holiday_date TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            holiday_type TEXT NOT NULL DEFAULT 'Regular',
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payroll_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Approved',
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS accounting_export_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            description TEXT NOT NULL,
            debit_account TEXT NOT NULL,
            credit_account TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'For Review',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS integration_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            external_source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            source_type TEXT,
            source_id INTEGER,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Ready',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            sent_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(external_source, external_id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT,
            action TEXT NOT NULL,
            table_name TEXT,
            record_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_time_logs_emp_date ON time_logs(employee_id, work_date);
        CREATE INDEX IF NOT EXISTS idx_schedules_emp_date ON schedules(employee_id, work_date);
        CREATE INDEX IF NOT EXISTS idx_scheduled_shifts_emp_date ON scheduled_shifts(employee_id, shift_date);
        CREATE INDEX IF NOT EXISTS idx_leave_requests_emp_dates ON leave_requests(employee_id, start_date, end_date, status);
        CREATE INDEX IF NOT EXISTS idx_payroll_items_run_emp ON payroll_items(payroll_run_id, employee_id);
        CREATE INDEX IF NOT EXISTS idx_payroll_corrections_run ON payroll_corrections(payroll_run_id);
        CREATE INDEX IF NOT EXISTS idx_payroll_corrections_status ON payroll_corrections(status, apply_to_next_run);
        CREATE INDEX IF NOT EXISTS idx_payroll_adjustments_emp_period ON payroll_adjustments(employee_id, period_start, period_end, status);
        CREATE INDEX IF NOT EXISTS idx_accounting_export_source ON accounting_export_queue(source_type, source_id, status);
        CREATE INDEX IF NOT EXISTS idx_integration_outbox_status ON integration_outbox(status, event_type, external_id);
        CREATE INDEX IF NOT EXISTS idx_drawer_movements_source ON cash_drawer_movements(source_type, source_id, status);
        CREATE INDEX IF NOT EXISTS idx_13th_employee_year ON payroll_13th_month_runs(employee_id, year, status);
        """
    )
    run_schema_migrations(conn)
    seed_defaults(conn)
    conn.commit()


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings(key, value, updated_at) VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, now_iso()),
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def seed_defaults(conn: sqlite3.Connection) -> None:
    now = now_iso()
    settings = {
        "standard_daily_paid_hours": "8",
        "standard_shift_hours": "9",
        "standard_break_minutes": "60",
        "night_diff_start": "22:00",
        "night_diff_end": "06:00",
        "night_diff_rate": "0.10",
        "ot_rate": "1.25",
        "philhealth_rate": "0.05",
        "philhealth_floor": "10000",
        "philhealth_ceiling": "100000",
        "pagibig_rate": "0.02",
        "pagibig_employer_rate": "0.02",
        "pagibig_ceiling": "10000",
        "sss_method": "actual_month_to_date_catch_up",
        "philhealth_basis": "declared_monthly_split",
        "pagibig_basis": "declared_monthly_split",
        "regular_holiday_multiplier": "2.00",
        "special_holiday_multiplier": "1.30",
        "rest_day_multiplier": "1.30",
        "regular_holiday_rest_day_multiplier": "2.60",
        "special_holiday_rest_day_multiplier": "1.50",
        "premium_day_ot_rate": "1.30",
        "payroll_cash_account": "Payroll Bank / Cash",
        "company_name": "Hidden Oasis",
        "company_address": "Gingoog City, Misamis Oriental",
        "13th_month_basis": "regular_pay_plus_paid_leave_only",
        "current_user": "Caryl / Owner",
        "current_role": "Owner",
        "main_drawer_name": "Main Drawer",
        "drawer_cash_account": "Cash in Drawer",
        "employee_ca_account": "Employee Cash Advance Receivable",
        "salary_expense_account": "Salaries and Wages Expense",
        "salary_payable_account": "Salaries Payable",
        "employer_contribution_expense_account": "Employer Contributions Expense",
        "accounting_api_base_url": "http://localhost:8000/api",
        "pos_api_base_url": "http://localhost:8001/api",
        "operations_api_base_url": "http://localhost:8002/api",
        "integration_api_key": os.getenv("INTEGRATION_API_KEY", "replace-with-shared-secret"),
        "payroll_external_source": "hidden_oasis_staff_payroll",
    }
    for k, v in settings.items():
        conn.execute(
            "INSERT OR IGNORE INTO app_settings(key, value, updated_at) VALUES(?,?,?)",
            (k, v, now),
        )

    for dept in ["Reception", "Housekeeping", "Kitchen", "Cafe", "Security", "Admin", "Freelance"]:
        conn.execute("INSERT OR IGNORE INTO departments(name, active) VALUES(?,1)", (dept,))

    leave_types = [
        ("Service Incentive Leave", 5, 1, 1, 1, 0, 1, "Default Philippine SIL bucket; entitlement can be toggled per employee."),
        ("Sick Leave", 0, 1, 0, 1, 0, 1, "Company-controlled leave; configure credits per employee."),
        ("Vacation Leave", 0, 1, 0, 1, 0, 1, "Company-controlled leave; configure credits per employee."),
        ("Emergency Leave", 0, 1, 0, 1, 0, 1, "Company-controlled leave; configure credits per employee."),
        ("Bereavement Leave", 0, 1, 0, 1, 0, 1, "Company-controlled unless policy provides credits."),
        ("Unpaid Leave", 0, 0, 0, 1, 0, 0, "No paid credits; used to classify approved unpaid absence."),
        ("Maternity Leave", 105, 1, 1, 1, 1, 0, "Track entitlement and documentation separately."),
        ("Paternity Leave", 7, 1, 1, 1, 1, 0, "Track entitlement and documentation separately."),
        ("Solo Parent Leave", 7, 1, 1, 1, 1, 1, "Enable only for entitled employees."),
        ("VAWC Leave", 10, 1, 1, 1, 1, 0, "Enable only for entitled employees."),
        ("Special Leave for Women", 60, 1, 1, 1, 1, 0, "Enable only for entitled employees."),
        ("AWOL", 0, 0, 0, 1, 0, 0, "No-pay absence classification."),
        ("Suspension", 0, 0, 0, 1, 0, 0, "No-pay disciplinary status."),
    ]
    for lt in leave_types:
        conn.execute(
            """
            INSERT OR IGNORE INTO leave_types
            (name, default_credits, paid, statutory, requires_approval, requires_attachment, annual_reset, notes)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            lt,
        )

    for name, rate in [("Pubmat", 150.0), ("Video Edit", 0.0), ("Reel", 0.0), ("Custom Output", 0.0)]:
        conn.execute(
            "INSERT OR IGNORE INTO freelance_rate_types(name, rate, active) VALUES(?,?,1)",
            (name, rate),
        )

    conn.execute(
        "INSERT OR IGNORE INTO biometric_import_profiles(profile_name, import_mode, created_at) VALUES(?,?,?)",
        ("Basic CSV/Excel Upload", "Timestamp Rows", now),
    )

    # Starter 2025-style SSS table generator: editable and replaceable with exact official table as needed.
    # Employee share is 5% of MSC; employer share is 10% of MSC; EC stored separately as placeholder.
    if conn.execute("SELECT COUNT(*) FROM sss_contribution_table").fetchone()[0] == 0:
        start = 5000
        end = 35000
        step = 500
        lower = 0
        msc = start
        while msc <= end:
            if msc == start:
                min_comp, max_comp = 0, 5249.99
            elif msc == end:
                min_comp, max_comp = 34750, 10**9
            else:
                min_comp, max_comp = msc - 250, msc + 249.99
            ee = round(msc * 0.05, 2)
            er = round(msc * 0.10, 2)
            ec = 10.0 if msc < 15000 else 30.0
            conn.execute(
                """
                INSERT INTO sss_contribution_table(min_comp, max_comp, msc, ee_share, er_share, ec_share, active)
                VALUES(?,?,?,?,?,?,1)
                """,
                (min_comp, max_comp, msc, ee, er, ec),
            )
            msc += step
