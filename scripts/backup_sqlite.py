#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(os.getenv("STAFF_PAYROLL_DB_PATH", "data/staff_payroll.sqlite"))
DEFAULT_BACKUP_DIR = Path(os.getenv("STAFF_PAYROLL_BACKUP_DIR", "backups"))


def verify_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError(f"SQLite integrity check failed for {path}: {result}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify a timestamped SQLite backup for Hidden Oasis payroll.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--keep", type=int, default=30, help="Number of newest backups to keep.")
    args = parser.parse_args()

    db_path = args.db.expanduser().resolve()
    backup_dir = args.backup_dir.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    verify_sqlite(db_path)

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{db_path.stem}-{stamp}.sqlite"
    shutil.copy2(db_path, target)
    verify_sqlite(target)

    backups = sorted(backup_dir.glob(f"{db_path.stem}-*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[max(args.keep, 0):]:
        old.unlink(missing_ok=True)

    print(f"Backup created and verified: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
