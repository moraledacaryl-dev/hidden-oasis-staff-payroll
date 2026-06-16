#!/usr/bin/env python3
"""Create a read-only backup/export package for the Staff Payroll SQLite database.

This script does not modify the source database. It opens SQLite in read-only mode,
creates a timestamped output folder, copies the database file, exports every user
table to CSV, exports schema SQL, and writes a manifest with row counts and hashes.

Default source database:
    data/staff_payroll.sqlite

Example:
    python scripts/export_staff_payroll_backup.py

Example with explicit paths:
    python scripts/export_staff_payroll_backup.py \
      --db data/staff_payroll.sqlite \
      --out data/backups
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB_PATH = Path("data/staff_payroll.sqlite")
DEFAULT_OUT_ROOT = Path("data/backups")


@dataclass
class TableExport:
    table: str
    row_count: int
    csv_file: str
    columns: list[str]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name: str) -> str:
    allowed = []
    for char in name:
        if char.isalnum() or char in {"_", "-"}:
            allowed.append(char)
        else:
            allowed.append("_")
    cleaned = "".join(allowed).strip("_")
    return cleaned or "table"


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.resolve()
    uri = f"file:{resolved}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def fetch_user_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [row[0] for row in rows]


def fetch_schema(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    sections: list[str] = []
    for object_type, name, sql in rows:
        sections.append(f"-- {object_type}: {name}\n{sql};\n")
    return "\n".join(sections)


def export_table(conn: sqlite3.Connection, table: str, csv_dir: Path) -> TableExport:
    quoted_table = quote_identifier(table)
    cursor = conn.execute(f"SELECT * FROM {quoted_table}")
    columns = [description[0] for description in cursor.description or []]
    csv_path = csv_dir / f"{safe_name(table)}.csv"

    row_count = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            writer.writerows(rows)
            row_count += len(rows)

    return TableExport(
        table=table,
        row_count=row_count,
        csv_file=str(csv_path.relative_to(csv_dir.parent)),
        columns=columns,
    )


def run_integrity_check(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    return [str(row[0]) for row in rows]


def build_manifest(
    *,
    db_path: Path,
    db_copy_path: Path,
    output_dir: Path,
    table_exports: Iterable[TableExport],
    integrity_check: list[str],
) -> dict[str, Any]:
    source_stat = db_path.stat()
    copy_stat = db_copy_path.stat()
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_database": str(db_path),
        "output_dir": str(output_dir),
        "source_database_size_bytes": source_stat.st_size,
        "database_copy_size_bytes": copy_stat.st_size,
        "source_database_sha256": sha256_file(db_path),
        "database_copy_sha256": sha256_file(db_copy_path),
        "sqlite_integrity_check": integrity_check,
        "tables": [asdict(item) for item in table_exports],
        "notes": [
            "Source database was opened in SQLite read-only mode.",
            "This backup package is for migration verification and rollback safety.",
            "Do not commit generated backup output folders to GitHub if they contain real staff payroll data.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Staff Payroll SQLite database safely.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path. Default: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help=f"Backup output root. Default: {DEFAULT_OUT_ROOT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path: Path = args.db
    out_root: Path = args.out

    if not db_path.exists():
        raise SystemExit(f"Database file not found: {db_path}")
    if not db_path.is_file():
        raise SystemExit(f"Database path is not a file: {db_path}")

    backup_dir = out_root / f"staff_payroll_backup_{utc_timestamp()}"
    csv_dir = backup_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=False)

    db_copy_path = backup_dir / db_path.name
    shutil.copy2(db_path, db_copy_path)

    with connect_read_only(db_path) as conn:
        integrity_check = run_integrity_check(conn)
        schema_sql = fetch_schema(conn)
        (backup_dir / "schema.sql").write_text(schema_sql, encoding="utf-8")

        table_exports: list[TableExport] = []
        for table in fetch_user_tables(conn):
            table_exports.append(export_table(conn, table, csv_dir))

    manifest = build_manifest(
        db_path=db_path,
        db_copy_path=db_copy_path,
        output_dir=backup_dir,
        table_exports=table_exports,
        integrity_check=integrity_check,
    )
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Backup/export complete: {backup_dir}")
    print(f"Tables exported: {len(table_exports)}")
    print(f"Integrity check: {', '.join(integrity_check)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
