#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import SESSION_TTL_SECONDS, sign_payload
from api.staff_self_service import ensure_schema as ensure_staff_self_service_schema
from core.db import get_conn, init_db, now_iso

MANILA = ZoneInfo("Asia/Manila")


def manila_today():
    return datetime.now(MANILA).date()


def main() -> int:
    if os.getenv("STAFF_PAYROLL_ENV", "development").strip().lower() == "production":
        raise SystemExit("Browser smoke seeding is disabled in production.")

    raw_db_path = os.getenv("STAFF_PAYROLL_DB_PATH")
    if not raw_db_path:
        raise SystemExit("STAFF_PAYROLL_DB_PATH must point to a disposable database.")
    if not os.getenv("STAFF_PAYROLL_SESSION_SECRET"):
        raise SystemExit("STAFF_PAYROLL_SESSION_SECRET is required.")

    db_path = Path(raw_db_path).expanduser().resolve()
    if db_path.exists():
        raise SystemExit(f"Refusing to replace existing database: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_conn(db_path)
    try:
        init_db(conn)
        ensure_staff_self_service_schema(conn)
        created_at = now_iso()
        supervisor_employee_id = int(
            conn.execute(
                """
                INSERT INTO employees(
                    employee_code, full_name, department, position, status,
                    created_at, updated_at
                ) VALUES('SMOKE-GM','Browser General Manager With An Intentionally Long Hospitality Operations Name','Guest Experience and Resort Operations',
                         'General Manager for Guest Experience and Resort Operations','Active',?,?)
                """,
                (created_at, created_at),
            ).lastrowid
        )
        staff_employee_id = int(
            conn.execute(
                """
                INSERT INTO employees(
                    employee_code, full_name, department, position, status,
                    created_at, updated_at
                ) VALUES('SMOKE-STAFF','Browser Staff Member With An Intentionally Long Front Office Name','Reservations and Guest Experience',
                         'Front Desk Receptionist and Reservations Coordinator','Active',?,?)
                """,
                (created_at, created_at),
            ).lastrowid
        )
        users = (
            ("Browser Owner", "Owner", None, 1),
            ("Browser General Manager With An Intentionally Long Hospitality Operations Name", "General Manager", supervisor_employee_id, 1),
            ("Browser Staff Member With An Intentionally Long Front Office Name", "Staff", staff_employee_id, 0),
        )
        user_ids: dict[str, int] = {}
        for display_name, role, employee_id, mfa_enabled in users:
            user_id = int(
                conn.execute(
                    """
                    INSERT INTO app_users(
                        display_name, role, active, created_at, must_change_password,
                        employee_id, session_version, mfa_enabled, mfa_confirmed_at
                    ) VALUES(?, ?, 1, ?, 0, ?, 1, ?, ?)
                    """,
                    (
                        display_name,
                        role,
                        created_at,
                        employee_id,
                        mfa_enabled,
                        created_at if mfa_enabled else None,
                    ),
                ).lastrowid
            )
            role_key = {
                "Owner": "owner",
                "General Manager": "supervisor",
                "Staff": "staff",
            }[role]
            user_ids[role_key] = user_id

        today = manila_today()
        week_start = today - timedelta(days=today.weekday())
        monday = week_start.isoformat()
        tuesday = (week_start + timedelta(days=1)).isoformat()
        conn.executemany(
            """
            INSERT INTO scheduled_shifts(
                employee_id, shift_date, start_time, end_time, position, department,
                break_minutes, status, notes, source
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 'Draft', ?, ?)
            """,
            (
                (
                    supervisor_employee_id, monday, "07:30", "18:45",
                    "Guest Experience Supervisor", "Operations", 90,
                    "Coordinate VIP arrivals, airport transfers, and afternoon event turnover.",
                    "planned",
                ),
                (
                    supervisor_employee_id, tuesday, "22:00", "06:30",
                    "Night Operations Manager", "Operations", 45,
                    "Overnight coverage with end-of-day reconciliation and security handoff.",
                    "planned",
                ),
                (
                    staff_employee_id, monday, "08:15", "17:45",
                    "Front Desk Receptionist", "Operations", 60,
                    "Morning opening, guest check-ins, phone coverage, and booking updates.",
                    "planned",
                ),
                (
                    staff_employee_id, tuesday, "10:00", "19:30",
                    "Reservations and Guest Services", "Operations", 30,
                    "Group reservation follow-ups and late-arrival coordination.",
                    "imported",
                ),
            ),
        )
        conn.executemany(
            """
            INSERT INTO time_logs(
                employee_id, work_date, actual_in, actual_out, source,
                approved_ot_hours, attendance_status, notes, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    supervisor_employee_id, monday, "07:24", "19:18", "manual",
                    1.25, "Approved", "Extended shift for event turnover.", created_at, created_at,
                ),
                (
                    supervisor_employee_id, tuesday, "21:52", "06:47", "manual",
                    0.5, "For Review", "Overnight actual awaiting final review.", created_at, created_at,
                ),
                (
                    staff_employee_id, monday, "08:22", "18:03", "manual",
                    0.75, "Approved", "Late checkout support.", created_at, created_at,
                ),
                (
                    staff_employee_id, tuesday, "10:08", "19:51", "biometric",
                    0.25, "Pending", "Biometric import pending supervisor review.", created_at, created_at,
                ),
            ),
        )
        shift_row = conn.execute(
            "SELECT id FROM scheduled_shifts WHERE employee_id=? AND shift_date=? ORDER BY id LIMIT 1",
            (staff_employee_id, monday),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO shift_change_requests(
                request_no, employee_id, shift_id, request_type,
                original_date, original_start_time, original_end_time,
                requested_date, requested_start_time, requested_end_time,
                reason, status, emergency, accuracy_confirmed,
                employee_notified, coverage_confirmed,
                submitted_by_user_id, submitted_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', 0, 1, 0, 0, ?, ?)
            """,
            (
                "SMOKE-SHIFT-001", staff_employee_id, int(shift_row[0]), "Schedule adjustment",
                monday, "08:15", "17:45", monday, "09:00", "18:00",
                "Browser smoke request for responsive drawer verification only.",
                user_ids["staff"], created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO cash_advances(
                employee_id, request_date, amount, status, outstanding_balance, created_at
            ) VALUES(?, ?, 2500, 'Active', 1750, ?)
            """,
            (staff_employee_id, monday, created_at),
        )
        # Synthetic historical manual receipt with no Staff Accounting
        # outbox record: confirms the read-only review queue renders even for
        # a fully paid advance. This test fixture never touches production.
        exception_advance_id = int(conn.execute(
            """
            INSERT INTO cash_advances(
                employee_id, request_date, advance_date, amount, status,
                outstanding_balance, remaining_balance, ledger_opening_balance,
                created_at
            ) VALUES(?, ?, ?, 1200, 'Fully Paid', 0, 0, 1200, ?)
            """,
            (staff_employee_id, monday, monday, created_at),
        ).lastrowid)
        conn.execute(
            """
            INSERT INTO cash_advance_repayments(
                cash_advance_id, employee_id, repayment_date, amount, source,
                payment_method, method, active, created_at
            ) VALUES(?, ?, ?, 1200, 'Manual', 'Cash', 'Cash', 1, ?)
            """,
            (exception_advance_id, monday, created_at),
        )
        payroll_run_id = int(
            conn.execute(
                """
                INSERT INTO payroll_runs(
                    period_start, period_end, payout_date, run_label, status,
                    prepared_by, validation_summary, created_at
                ) VALUES(?, ?, ?, 'Browser Smoke', 'Draft', 'Browser Owner', 'Smoke fixture ready for review.', ?)
                """,
                (monday, tuesday, (week_start + timedelta(days=2)).isoformat(), created_at),
            ).lastrowid
        )
        for employee_id, gross, deductions, net, warning in (
            (supervisor_employee_id, 6850.75, 975.25, 5875.50, "Review overnight overtime before approval."),
            (staff_employee_id, 4325.50, 525.00, 3800.50, ""),
        ):
            conn.execute(
                """
                INSERT INTO payroll_items(
                    payroll_run_id, employee_id, regular_hours, regular_pay,
                    approved_ot_hours, ot_pay, night_diff_hours, night_diff_pay,
                    gross_pay, sss_ee, philhealth_ee, pagibig_ee,
                    total_deductions, net_pay, warnings, created_at
                ) VALUES(?, ?, 16, ?, 1.25, 250, 2.5, 75, ?, 300, 175, 50, ?, ?, ?, ?)
                """,
                (payroll_run_id, employee_id, gross - 325, gross, deductions, net, warning, created_at),
            )
        conn.execute(
            """
            INSERT INTO payroll_corrections(
                payroll_run_id, employee_id, adjustment_type, amount, reason,
                apply_to_next_run, status, created_by, created_at
            ) VALUES(?, ?, 'Note', 0, ?, 0, 'Recorded', 'Browser Owner', ?)
            """,
            (
                payroll_run_id, supervisor_employee_id,
                "Browser smoke correction with intentionally descriptive audit text for responsive layout verification.",
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    issued_at = int(time.time())
    tokens = {
        role: sign_payload(
            {
                "sub": user_id,
                "role": role,
                "sv": 1,
                "iat": issued_at,
                "exp": issued_at + SESSION_TTL_SECONDS,
            }
        )
        for role, user_id in user_ids.items()
    }
    print(json.dumps({"tokens": tokens, "payroll_run_id": payroll_run_id}, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
