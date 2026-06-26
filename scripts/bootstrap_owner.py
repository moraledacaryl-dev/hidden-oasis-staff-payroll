#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audit import log_audit
from core.auth import provision_owner
from core.db import DB_PATH, get_conn, init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or reset the owner login.")
    parser.add_argument("--name", default="Owner", help="Owner login name.")
    parser.add_argument(
        "--keep-password",
        action="store_true",
        help="Do not require a password change on first sign-in.",
    )
    args = parser.parse_args()
    password = getpass.getpass("New owner password (12+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    conn = get_conn(DB_PATH)
    try:
        init_db(conn)
        user_id = provision_owner(
            conn,
            args.name,
            password,
            must_change=not args.keep_password,
        )
        log_audit(
            conn,
            actor="bootstrap_owner.py",
            action="Owner account provisioned",
            table_name="app_users",
            record_id=user_id,
        )
        conn.commit()
    finally:
        conn.close()
    print(f"Owner account ready: {args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
