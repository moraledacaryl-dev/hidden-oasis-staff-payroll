#!/usr/bin/env python3
"""Fail deployment before pip installs or backups when storage is insufficient.

This is a read-only early gate. scripts/production_preflight.py remains the
authoritative comprehensive production check later in the deployment.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


GIB = 1024**3


def configured_limit(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return max(minimum, default)


def existing_ancestor(path: Path) -> Path:
    current = path.expanduser().resolve()
    while not current.exists():
        if current == current.parent:
            raise FileNotFoundError(f"No existing filesystem ancestor for {path}")
        current = current.parent
    return current


def capacity_status(
    paths: list[Path],
    *,
    min_bytes: int,
    min_percent: int,
    min_inode_percent: int,
) -> list[dict[str, object]]:
    """Read free space/inodes once per filesystem, without making changes."""
    checked: set[int] = set()
    results: list[dict[str, object]] = []
    for path in paths:
        anchor = existing_ancestor(path)
        device = anchor.stat().st_dev
        if device in checked:
            continue
        checked.add(device)
        usage = shutil.disk_usage(anchor)
        free_percent = int(usage.free * 100 / usage.total) if usage.total else 0
        statvfs = os.statvfs(anchor)
        free_inodes_percent = (
            int(statvfs.f_favail * 100 / statvfs.f_files) if statvfs.f_files else 100
        )
        results.append(
            {
                "path": str(anchor),
                "free_bytes": usage.free,
                "free_percent": free_percent,
                "free_inodes_percent": free_inodes_percent,
                "ok": (
                    usage.free >= min_bytes
                    and free_percent >= min_percent
                    and free_inodes_percent >= min_inode_percent
                ),
            }
        )
    return results


def main() -> int:
    db_path = os.getenv("STAFF_PAYROLL_DB_PATH", "").strip()
    backup_dir = os.getenv("STAFF_PAYROLL_BACKUP_DIR", "").strip()
    if not db_path or not backup_dir:
        print("FAIL: database and backup path environment variables must be configured.", file=sys.stderr)
        return 1

    app_root = Path(os.getenv("APP_ROOT", "/root/repos/hidden-oasis-staff-payroll"))
    runtime_base = Path(os.getenv("RUNTIME_BASE", "/opt/hiddenoasis/staff-payroll"))
    paths = [Path(db_path).parent, Path(backup_dir), app_root, runtime_base]
    minimum_bytes = configured_limit("STAFF_PAYROLL_MIN_FREE_DISK_BYTES", 2 * GIB)
    minimum_percent = configured_limit("STAFF_PAYROLL_MIN_FREE_DISK_PERCENT", 10)
    minimum_inodes = configured_limit("STAFF_PAYROLL_MIN_FREE_INODE_PERCENT", 10)
    try:
        results = capacity_status(
            paths,
            min_bytes=minimum_bytes,
            min_percent=minimum_percent,
            min_inode_percent=minimum_inodes,
        )
    except OSError as exc:
        print(f"FAIL: cannot inspect deployment filesystem: {exc}", file=sys.stderr)
        return 1

    for row in results:
        label = "PASS" if row["ok"] else "FAIL"
        gib = int(row["free_bytes"]) / GIB
        print(
            f"{label} early disk capacity {row['path']}: "
            f"{gib:.2f} GiB free ({row['free_percent']}%), "
            f"inodes {row['free_inodes_percent']}% free"
        )

    if not results or not all(row["ok"] for row in results):
        print(
            "Early disk preflight failed. No new backup, virtual environment, "
            "node_modules or staged release was created. Free space without "
            "deleting the active database, uploaded documents or only recoverable backup.",
            file=sys.stderr,
        )
        return 1
    print("Early disk capacity preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
