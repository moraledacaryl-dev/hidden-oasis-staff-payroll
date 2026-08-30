from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import FileResponse

from api.payroll_drafts import must_be_payroll_user
from api.security import current_user_from_token, require_api_key
from core.audit import log_audit
from core.backups import BackupVerificationError, backup_path, create_backup_package, list_backups, verify_backup
from core.db import DB_PATH, fetchone, get_conn
from core.observability import normalize_request_id, parse_timestamp_utc, utc_iso, utc_now

router = APIRouter(prefix="/api/v1")


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def table_count(conn, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = fetchone(conn, f"SELECT COUNT(*) AS c FROM {table}") or {}
    return int(row.get("c") or 0)


def require_owner(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Owner access required.")
    return user


def database_checks(conn) -> dict[str, Any]:
    integrity = str(conn.execute("PRAGMA quick_check").fetchone()[0])
    write_ok = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS health_write_test(value INTEGER)")
        conn.rollback()
        write_ok = True
    except sqlite3.Error:
        conn.rollback()
    migration = fetchone(conn, "SELECT MAX(version) AS version FROM schema_migrations") if table_exists(conn, "schema_migrations") else None
    return {"integrity": integrity, "writable": write_ok, "migration_version": int((migration or {}).get("version") or 0)}


def backup_age_hours(created_at: str) -> float:
    created = parse_timestamp_utc(created_at)
    return round(max(0.0, (utc_now() - created).total_seconds()) / 3600, 1)


@router.get("/production/health")
def production_health(
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> dict[str, Any]:
    user = must_be_payroll_user(authorization, x_api_key)
    request_id = normalize_request_id(x_request_id)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Request-ID"] = request_id

    db_path = Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DB_PATH))).expanduser()
    backup_dir = Path(os.getenv("STAFF_PAYROLL_BACKUP_DIR", "backups")).expanduser()
    backups = list_backups()
    conn = get_conn(db_path)
    try:
        checks = database_checks(conn)
        latest_backup = backups[0] if backups else None
        age_hours = backup_age_hours(str(latest_backup["created_at"])) if latest_backup else None
        return {
            "ok": checks["integrity"].lower() == "ok" and checks["writable"],
            "checked_at": utc_iso(),
            "request_id": request_id,
            "checked_by": user.get("display_name"),
            "database_path": str(db_path),
            "database_exists": db_path.exists(),
            "backup_dir": str(backup_dir),
            "backup_count": len(backups),
            "latest_backup": latest_backup,
            "backup_age_hours": age_hours,
            "backup_encryption_configured": bool(os.getenv("STAFF_PAYROLL_BACKUP_KEY")),
            "offsite_backup_configured": bool(os.getenv("STAFF_PAYROLL_OFFSITE_BACKUP_DIR")),
            "database_checks": checks,
            "tables": {
                "payroll_runs": table_exists(conn, "payroll_runs"),
                "payroll_items": table_exists(conn, "payroll_items"),
                "scheduled_shifts": table_exists(conn, "scheduled_shifts"),
                "time_logs": table_exists(conn, "time_logs"),
                "schedule_change_logs": table_exists(conn, "schedule_change_logs"),
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
            "mode": "live_production_health",
        }
    finally:
        conn.close()


@router.get("/production/backups")
def backups(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    require_owner(authorization, x_api_key)
    return {"ok": True, "items": list_backups()}


@router.post("/production/backups")
def make_backup(authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_owner(authorization, x_api_key)
    item = create_backup_package(Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DB_PATH))).expanduser())
    conn = get_conn(DB_PATH)
    try:
        log_audit(conn, actor=user.get("display_name"), action="Operational backup package created", table_name="backups", details={"name": item["name"], "encrypted": item["encrypted"], "attachment_count": item.get("attachment_count")})
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "item": item}


@router.post("/production/backups/{name}/verify")
def verify_named_backup(name: str, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    user = require_owner(authorization, x_api_key)
    try:
        result = verify_backup(backup_path(name))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (BackupVerificationError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conn = get_conn(DB_PATH)
    try:
        log_audit(conn, actor=user.get("display_name"), action="Backup verified", table_name="backups", details={"name": name})
        conn.commit()
    finally:
        conn.close()
    return result


@router.get("/production/backups/{name}/download")
def download_backup(name: str, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    require_owner(authorization, x_api_key)
    try:
        path = backup_path(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup not found.")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
