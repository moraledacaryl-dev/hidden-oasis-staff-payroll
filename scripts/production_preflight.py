#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backups import backup_path, list_backups, verify_backup
from core.db import MIGRATIONS
from core.offsite_backups import verify_offsite_copy
from core.runtime_guard import validate_runtime_environment

DB = Path(os.getenv("STAFF_PAYROLL_DB_PATH", "data/staff_payroll.sqlite"))
REQUIRED = [
    "app_users",
    "employees",
    "payroll_runs",
    "payroll_items",
    "scheduled_shifts",
    "time_logs",
    "schedule_change_logs",
    "legacy_schedule_ignores",
    "payroll_revision_change_links",
]
ACTIVE_OUTBOX_STATUSES = ("Pending", "Retry", "Processing", "Ready", "Error")


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def print_status(ok: bool, label: str) -> int:
    print(("OK   " if ok else "FAIL ") + label)
    return 0 if ok else 1


def env_int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return max(minimum, default)


def file_age_seconds(path: Path) -> float:
    return max(0.0, time.time() - path.stat().st_mtime)


def parse_marker_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def check_runtime_paths() -> int:
    failures = 0
    values = {
        "database": os.getenv("STAFF_PAYROLL_DB_PATH", "").strip(),
        "uploads": os.getenv("STAFF_UPLOAD_DIR", "").strip(),
        "backup": os.getenv("STAFF_PAYROLL_BACKUP_DIR", "").strip(),
    }
    for label, raw in values.items():
        path = Path(raw).expanduser() if raw else None
        failures += print_status(bool(path and path.is_absolute()), f"absolute production {label} path")
        if path:
            target = path.parent if label == "database" else path
            failures += print_status(target.exists(), f"production {label} path exists: {target}")
            failures += print_status(os.access(target, os.W_OK), f"production {label} path writable")
    return failures


def check_public_url_and_cors() -> int:
    failures = 0
    public_url = os.getenv("PUBLIC_APP_URL", "").strip()
    parsed = urlparse(public_url)
    https_ok = parsed.scheme == "https" and bool(parsed.netloc)
    failures += print_status(https_ok, "PUBLIC_APP_URL uses HTTPS")

    origin = f"{parsed.scheme}://{parsed.netloc}" if https_ok else ""
    raw_cors = (
        os.getenv("STAFF_PAYROLL_CORS_ORIGINS", "").strip()
        or os.getenv("CORS_ORIGINS", "").strip()
        or os.getenv("ALLOWED_ORIGINS", "").strip()
    )
    origins = {item.strip().rstrip("/") for item in raw_cors.split(",") if item.strip()}
    failures += print_status(bool(origin and origin.rstrip("/") in origins), "public app origin allowed by CORS")
    return failures


def check_filesystem_capacity(paths: list[Path]) -> int:
    failures = 0
    min_free_bytes = env_int("STAFF_PAYROLL_MIN_FREE_DISK_BYTES", 2 * 1024**3)
    min_free_percent = env_int("STAFF_PAYROLL_MIN_FREE_DISK_PERCENT", 10)
    min_inode_percent = env_int("STAFF_PAYROLL_MIN_FREE_INODE_PERCENT", 10)
    seen: set[int] = set()
    for path in paths:
        try:
            stat = path.stat()
        except OSError as exc:
            print(f"     {path}: {exc}")
            failures += print_status(False, f"filesystem reachable: {path}")
            continue
        if stat.st_dev in seen:
            continue
        seen.add(stat.st_dev)
        usage = shutil.disk_usage(path)
        free_percent = int((usage.free * 100) / usage.total) if usage.total else 0
        failures += print_status(
            usage.free >= min_free_bytes and free_percent >= min_free_percent,
            f"disk capacity {path} ({free_percent}% free)",
        )
        vfs = os.statvfs(path)
        inode_percent = int((vfs.f_favail * 100) / vfs.f_files) if vfs.f_files else 100
        failures += print_status(
            inode_percent >= min_inode_percent,
            f"inode capacity {path} ({inode_percent}% free)",
        )
    return failures


def check_backup_recovery() -> int:
    failures = 0
    backup_key = os.getenv("STAFF_PAYROLL_BACKUP_KEY", "").strip()
    failures += print_status(bool(backup_key), "backup encryption key configured")

    items = list_backups()
    failures += print_status(bool(items), "at least one operational backup exists")
    if not items:
        return failures

    latest = items[0]
    latest_path = backup_path(str(latest["name"]))
    max_age_hours = env_int("STAFF_PAYROLL_MAX_BACKUP_AGE_HOURS", 26, minimum=1)
    failures += print_status(
        file_age_seconds(latest_path) <= max_age_hours * 3600,
        f"latest backup age <= {max_age_hours}h",
    )
    failures += print_status(bool(latest.get("encrypted")), "latest backup is encrypted")
    try:
        verified = verify_backup(latest_path)
        backup_verified = bool(verified.get("ok"))
    except Exception as exc:
        backup_verified = False
        print(f"     backup verification error: {exc}")
    failures += print_status(backup_verified, "latest backup verifies and contains a valid SQLite database")

    try:
        offsite = verify_offsite_copy(latest_path)
    except Exception as exc:
        offsite = {
            "configured": True,
            "exists": False,
            "matching": False,
            "destination": None,
            "last_modified": None,
        }
        print(f"     offsite verification error: {exc}")
    failures += print_status(bool(offsite.get("configured")), "offsite backup destination configured")
    if offsite.get("configured"):
        destination = str(offsite.get("destination") or "configured destination")
        failures += print_status(bool(offsite.get("exists")), f"matching latest offsite backup exists: {destination}")
        if offsite.get("exists"):
            last_modified = offsite.get("last_modified")
            recent = False
            if isinstance(last_modified, datetime):
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=timezone.utc)
                recent = (datetime.now(timezone.utc) - last_modified.astimezone(timezone.utc)).total_seconds() <= max_age_hours * 3600
            failures += print_status(recent, f"offsite backup age <= {max_age_hours}h")
            failures += print_status(bool(offsite.get("matching")), "offsite backup matches local encrypted backup")

    marker = Path(
        os.getenv(
            "STAFF_PAYROLL_RESTORE_DRILL_MARKER",
            "/var/lib/hiddenoasis/staff-payroll/restore-drill.json",
        )
    ).expanduser()
    failures += print_status(marker.is_file(), f"restore-drill marker exists: {marker}")
    if marker.is_file():
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            completed = parse_marker_time(str(payload.get("completed_at", "")))
            max_days = env_int("STAFF_PAYROLL_MAX_RESTORE_DRILL_AGE_DAYS", 31, minimum=1)
            age = datetime.now(timezone.utc) - completed
            marker_ok = (
                bool(payload.get("ok"))
                and str(payload.get("integrity", "")).lower() == "ok"
                and age.total_seconds() <= max_days * 86400
            )
            failures += print_status(marker_ok, f"restore drill successful within {max_days} days")
        except Exception as exc:
            print(f"     restore marker error: {exc}")
            failures += print_status(False, "restore-drill marker is valid JSON evidence")
    return failures


def check_schema_and_outbox(conn: sqlite3.Connection) -> int:
    failures = 0
    expected_versions = {int(version) for version, _, _ in MIGRATIONS}
    applied_versions = {
        int(row[0])
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    failures += print_status(expected_versions.issubset(applied_versions), f"schema migrations current through {max(expected_versions)}")

    if not table_exists(conn, "integration_outbox"):
        return failures + print_status(False, "integration_outbox table exists")

    placeholders = ",".join("?" for _ in ACTIVE_OUTBOX_STATUSES)
    active_count = int(
        conn.execute(
            f"SELECT COUNT(*) FROM integration_outbox WHERE status IN ({placeholders})",
            ACTIVE_OUTBOX_STATUSES,
        ).fetchone()[0]
    )
    max_active_age_minutes = env_int("STAFF_PAYROLL_MAX_ACTIVE_OUTBOX_AGE_MINUTES", 30, minimum=1)
    stale_active = int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM integration_outbox
            WHERE status IN ({placeholders})
              AND created_at < datetime('now', ?)
            """,
            (*ACTIVE_OUTBOX_STATUSES, f"-{max_active_age_minutes} minutes"),
        ).fetchone()[0]
    )
    print(f"INFO active integration outbox events: {active_count}")
    failures += print_status(stale_active == 0, f"no active outbox event older than {max_active_age_minutes} minutes")

    dead_letters = int(
        conn.execute("SELECT COUNT(*) FROM integration_outbox WHERE status='Dead Letter'").fetchone()[0]
    )
    max_dead_letters = env_int("STAFF_PAYROLL_MAX_DEAD_LETTERS", 10)
    print(f"INFO historical integration dead letters: {dead_letters}")
    failures += print_status(dead_letters <= max_dead_letters, f"dead-letter count <= configured maximum ({max_dead_letters})")
    return failures


def main() -> int:
    failures = 0
    db = DB.expanduser().resolve()
    failures += print_status(db.exists(), f"database exists: {db}")

    try:
        validate_runtime_environment()
        runtime_ok = True
    except RuntimeError as exc:
        runtime_ok = False
        print(f"     {exc}")
    failures += print_status(runtime_ok, "production runtime security configuration")
    failures += check_runtime_paths()
    failures += check_public_url_and_cors()

    try:
        server = importlib.import_module("api.server")
        entrypoint_ok = getattr(server, "app", None) is not None
    except Exception as exc:
        entrypoint_ok = False
        print(f"     {exc}")
    failures += print_status(entrypoint_ok, "canonical API entrypoint api.server:app")
    if not db.exists():
        return failures

    conn = sqlite3.connect(db)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        quick = conn.execute("PRAGMA quick_check").fetchone()
        failures += print_status(bool(integrity and str(integrity[0]).lower() == "ok"), "sqlite integrity")
        failures += print_status(bool(quick and str(quick[0]).lower() == "ok"), "sqlite quick_check")
        for table in REQUIRED:
            failures += print_status(table_exists(conn, table), f"table {table}")

        plaintext_mfa = conn.execute(
            """
            SELECT COUNT(*) FROM app_users
            WHERE mfa_secret IS NOT NULL
              AND TRIM(mfa_secret) <> ''
              AND mfa_secret NOT LIKE 'fernet:%'
            """
        ).fetchone()[0]
        failures += print_status(int(plaintext_mfa or 0) == 0, "no plaintext MFA secrets")
        failures += check_schema_and_outbox(conn)

        exact_duplicate_groups = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT employee_id, shift_date, start_time, end_time,
                     position, department, break_minutes, status,
                     COALESCE(notes, ''), COALESCE(legacy_schedule_id, -1), source,
                     COALESCE(review_status, ''), COALESCE(review_reason, ''),
                     COALESCE(reviewed_by, ''), COALESCE(reviewed_at, ''), approved_exception,
                     COUNT(*) AS c
              FROM scheduled_shifts
              GROUP BY employee_id, shift_date, start_time, end_time,
                       position, department, break_minutes, status,
                       COALESCE(notes, ''), COALESCE(legacy_schedule_id, -1), source,
                       COALESCE(review_status, ''), COALESCE(review_reason, ''),
                       COALESCE(reviewed_by, ''), COALESCE(reviewed_at, ''), approved_exception
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        failures += print_status(int(exact_duplicate_groups or 0) == 0, "no exact schedule duplicates")

        same_time_groups = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT employee_id, shift_date, start_time, end_time, COUNT(*) AS c
              FROM scheduled_shifts
              GROUP BY employee_id, shift_date, start_time, end_time
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        print(f"INFO same-time schedule groups requiring review: {int(same_time_groups or 0)}")
    finally:
        conn.close()

    backup_dir = Path(os.getenv("STAFF_PAYROLL_BACKUP_DIR", "backups")).expanduser()
    failures += check_filesystem_capacity([db.parent, backup_dir])
    failures += check_backup_recovery()

    compile_cmd = [
        sys.executable,
        "-m",
        "py_compile",
        "api/server.py",
        "api/employees.py",
        "api/schedules.py",
        "api/payroll_revision_controls.py",
        "api/production_health.py",
        "api/users.py",
        "core/runtime_guard.py",
        "core/mfa_security.py",
        "core/backups.py",
        "core/offsite_backups.py",
        "scripts/restore_drill.py",
    ]
    result = subprocess.run(compile_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    failures += print_status(result.returncode == 0, "python compile")
    if result.returncode != 0:
        print(result.stdout)

    if failures:
        print(f"Production preflight failed: {failures}")
        return 1
    print("Production preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
