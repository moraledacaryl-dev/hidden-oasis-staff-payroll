#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import SESSION_TTL_SECONDS, sign_payload
from core.db import get_conn, init_db, now_iso


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
        created_at = now_iso()
        supervisor_employee_id = int(
            conn.execute(
                """
                INSERT INTO employees(
                    employee_code, full_name, department, position, status,
                    created_at, updated_at
                ) VALUES('SMOKE-GM','Browser General Manager','Operations',
                         'General Manager','Active',?,?)
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
                ) VALUES('SMOKE-STAFF','Browser Staff','Operations',
                         'Staff','Active',?,?)
                """,
                (created_at, created_at),
            ).lastrowid
        )
        users = (
            ("Browser Owner", "Owner", None, 1),
            ("Browser General Manager", "General Manager", supervisor_employee_id, 1),
            ("Browser Staff", "Staff", staff_employee_id, 0),
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
    print(json.dumps(tokens, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
