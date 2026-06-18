#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def verify(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError(f"Integrity check failed for {path}: {result}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a verified SQLite backup.")
    parser.add_argument("backup", type=Path, help="Backup .sqlite file to restore from.")
    parser.add_argument("--target", type=Path, default=Path("data/staff_payroll.sqlite"))
    parser.add_argument("--yes", action="store_true", help="Confirm overwrite of the target database.")
    args = parser.parse_args()

    backup = args.backup.expanduser().resolve()
    target = args.target.expanduser().resolve()
    if not backup.exists():
        raise SystemExit(f"Backup not found: {backup}")
    if not args.yes:
        raise SystemExit("Refusing to overwrite target without --yes")

    verify(backup)
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_copy = target.with_name(f"{target.stem}-before-restore-{stamp}{target.suffix}")
        shutil.copy2(target, safety_copy)
        verify(safety_copy)
        print(f"Safety copy created: {safety_copy}")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    verify(target)
    print(f"Restored backup to: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
