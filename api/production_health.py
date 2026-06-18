from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header

from api.payroll_drafts import must_be_payroll_user
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def table_count(conn, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = fetchone(conn, f"SELECT COUNT(*) AS c FROM {table}") or {}
    return int(row.get("c") or 0)


@router.get("/production/health")
def production_health(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    db_path = Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DB_PATH))).expanduser()
    backup_dir = Path(os.getenv("STAFF_PAYROLL_BACKUP_DIR", "backups")).expanduser()
    backup_files = sorted(backup_dir.glob("*.sqlite"), key=lambda item: item.stat().st_mtime, reverse=True) if backup_dir.exists() else []
    conn = get_conn(db_path)
    try:
        return {
            "ok": True,
            "checked_by": user.get("display_name"),
            "database_path": str(db_path),
            "database_exists": db_path.exists(),
            "backup_dir": str(backup_dir),
            "backup_count": len(backup_files),
            "latest_backup": str(backup_files[0]) if backup_files else None,
            "tables": {
                "payroll_runs": table_exists(conn, "payroll_runs"),
                "payroll_items": table_exists(conn, "payroll_items"),
                "scheduled_shifts": table_exists(conn, "scheduled_shifts"),
                "time_logs": table_exists(conn, "time_logs"),
                "schedule_change_logs": table_exists(conn, "schedule_change_logs"),
                "legacy_schedule_ignores": table_exists(conn, "legacy_schedule_ignores"),
                "payroll_revision_change_links": table_exists(conn, "payroll_revision_change_links"),
            },
            "counts": {
                "payroll_runs": table_count(conn, "payroll_runs"),
                "scheduled_shifts": table_count(conn, "scheduled_shifts"),
                "time_logs": table_count(conn, "time_logs"),
                "schedule_change_logs": table_count(conn, "schedule_change_logs"),
            },
            "secrets_configured": {
                "STAFF_PAYROLL_API_KEY": bool(os.getenv("STAFF_PAYROLL_API_KEY")),
                "STAFF_PAYROLL_SESSION_SECRET": bool(os.getenv("STAFF_PAYROLL_SESSION_SECRET")),
            },
            "mode": "production_health_summary_no_secret_values",
        }
    finally:
        conn.close()
