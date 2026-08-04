#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "staff_payroll.sqlite"
OUTPUT_DIR = ROOT / "artifacts" / "production-baseline"
SERVICES = (
    "hiddenoasis-staff-api",
    "hiddenoasis-staff-web",
    "hiddenoasis-staff-integration-worker",
)
ENVIRONMENT_KEYS = (
    "STAFF_PAYROLL_ENV",
    "STAFF_PAYROLL_API_KEY",
    "STAFF_PAYROLL_SESSION_SECRET",
    "STAFF_PAYROLL_DB_PATH",
    "STAFF_PAYROLL_CORS_ORIGINS",
    "STAFF_PAYROLL_API_URL",
    "STAFF_PAYROLL_BACKUP_DIR",
    "STAFF_PAYROLL_BACKUP_KEY",
    "STAFF_PAYROLL_OFFSITE_BACKUP_DIR",
    "STAFF_PAYROLL_BACKUP_RETENTION",
)


def run(*args: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        return {"ok": result.returncode == 0, "code": result.returncode, "output": result.stdout.strip()}
    except FileNotFoundError:
        return {"ok": False, "code": 127, "output": f"command not found: {args[0]}"}


def git_state() -> dict[str, Any]:
    sha = run("git", "rev-parse", "HEAD")
    branch = run("git", "branch", "--show-current")
    status = run("git", "status", "--porcelain")
    origin = run("git", "rev-parse", "origin/main")
    return {
        "sha": sha["output"] if sha["ok"] else None,
        "branch": branch["output"] if branch["ok"] else None,
        "origin_main_sha": origin["output"] if origin["ok"] else None,
        "matches_origin_main": bool(sha["ok"] and origin["ok"] and sha["output"] == origin["output"]),
        "working_tree_clean": bool(status["ok"] and not status["output"]),
    }


def runtime_state() -> dict[str, Any]:
    node = run("node", "--version")
    npm = run("npm", "--version")
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "node": node["output"] if node["ok"] else None,
        "npm": npm["output"] if npm["ok"] else None,
    }


def database_state() -> dict[str, Any]:
    path = Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DEFAULT_DB))).expanduser().resolve()
    data: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return data
    conn = sqlite3.connect(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        migrations = []
        if "schema_migrations" in tables:
            migrations = [
                {"version": row[0], "name": row[1], "applied_at": row[2]}
                for row in conn.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY version")
            ]
        data.update(
            {
                "size_bytes": path.stat().st_size,
                "integrity": integrity[0] if integrity else None,
                "table_count": len(tables),
                "tables": tables,
                "schema_migrations": migrations,
            }
        )
    finally:
        conn.close()
    return data


def service_state() -> list[dict[str, Any]]:
    if not shutil.which("systemctl"):
        return [{"service": name, "available": False, "state": "systemctl unavailable"} for name in SERVICES]
    rows = []
    for name in SERVICES:
        active = run("systemctl", "is-active", name)
        enabled = run("systemctl", "is-enabled", name)
        rows.append(
            {
                "service": name,
                "available": True,
                "active": active["output"],
                "enabled": enabled["output"],
            }
        )
    return rows


def backup_state() -> dict[str, Any]:
    configured = os.getenv("STAFF_PAYROLL_BACKUP_DIR")
    path = Path(configured).expanduser().resolve() if configured else None
    result: dict[str, Any] = {"configured_path": str(path) if path else None, "exists": bool(path and path.exists())}
    if path and path.exists():
        files = sorted((item for item in path.iterdir() if item.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
        result["latest"] = [
            {
                "name": item.name,
                "size_bytes": item.stat().st_size,
                "modified_at": datetime.fromtimestamp(item.stat().st_mtime, timezone.utc).isoformat(),
            }
            for item in files[:10]
        ]
    return result


def environment_state() -> dict[str, Any]:
    return {key: {"configured": bool(os.getenv(key))} for key in ENVIRONMENT_KEYS}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_state(),
        "runtime": runtime_state(),
        "environment": environment_state(),
        "database": database_state(),
        "services": service_state(),
        "backups": backup_state(),
        "verification": {
            "production_preflight": run(sys.executable, "scripts/production_preflight.py"),
        },
    }
    destination = OUTPUT_DIR / f"baseline-{stamp}.json"
    latest = OUTPUT_DIR / "latest.json"
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    destination.write_text(rendered + "\n", encoding="utf-8")
    latest.write_text(rendered + "\n", encoding="utf-8")
    print(destination)
    return 0 if payload["verification"]["production_preflight"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
