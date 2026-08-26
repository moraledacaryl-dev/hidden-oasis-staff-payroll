#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backups import _read_backup_payload, backup_path, list_backups, verify_backup

REQUIRED_TABLES = {
    "app_users",
    "employees",
    "payroll_runs",
    "payroll_items",
    "integration_outbox",
}


def restored_database_from_backup(source: Path, temp_dir: Path) -> Path:
    payload, _ = _read_backup_payload(source)
    restored = temp_dir / "restored.sqlite"
    if source.name.endswith(".zip") or source.name.endswith(".zip.fernet"):
        package = temp_dir / "backup.zip"
        package.write_bytes(payload)
        with zipfile.ZipFile(package) as archive:
            restored.write_bytes(archive.read("database/staff-payroll.sqlite"))
    else:
        restored.write_bytes(payload)
    return restored


def main() -> int:
    backups = list_backups()
    if not backups:
        print("Restore drill failed: no backup exists", file=sys.stderr)
        return 1

    latest = backups[0]
    source = backup_path(str(latest["name"]))
    verified = verify_backup(source)

    with tempfile.TemporaryDirectory(prefix="staff-payroll-restore-drill-") as raw_temp:
        temp_dir = Path(raw_temp)
        restored = restored_database_from_backup(source, temp_dir)
        conn = sqlite3.connect(restored)
        try:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = sorted(REQUIRED_TABLES - tables)
            employees = int(conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0])
            payroll_runs = int(conn.execute("SELECT COUNT(*) FROM payroll_runs").fetchone()[0])
        finally:
            conn.close()

    ok = integrity.lower() == "ok" and quick.lower() == "ok" and not missing
    evidence = {
        "ok": ok,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backup_name": source.name,
        "backup_encrypted": bool(verified.get("encrypted")),
        "integrity": integrity,
        "quick_check": quick,
        "missing_required_tables": missing,
        "table_count": int(verified.get("table_count", 0)),
        "employees": employees,
        "payroll_runs": payroll_runs,
    }

    marker = Path(
        os.getenv(
            "STAFF_PAYROLL_RESTORE_DRILL_MARKER",
            "/var/lib/hiddenoasis/staff-payroll/restore-drill.json",
        )
    ).expanduser()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    marker.chmod(0o600)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
