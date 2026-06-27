from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import DB_PATH


def backup_directory() -> Path:
    return Path(os.getenv("STAFF_PAYROLL_BACKUP_DIR", "backups")).expanduser()


def _fernet(secret: str):
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("Install the cryptography package to create encrypted backups.") from exc
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _verify_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {result}")
    finally:
        conn.close()


def _plain_backup(source: Path, target: Path) -> None:
    source_conn = sqlite3.connect(str(source))
    target_conn = sqlite3.connect(str(target))
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    _verify_sqlite(target)


def create_backup(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    source = Path(db_path).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")

    directory = backup_directory()
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    secret = os.getenv("STAFF_PAYROLL_BACKUP_KEY", "").strip()
    suffix = ".sqlite.fernet" if secret else ".sqlite"
    target = directory / f"staff-payroll-{timestamp}{suffix}"

    with tempfile.TemporaryDirectory(prefix="staff-payroll-backup-") as temp_dir:
        plain = Path(temp_dir) / "staff-payroll.sqlite"
        _plain_backup(source, plain)
        if secret:
            target.write_bytes(_fernet(secret).encrypt(plain.read_bytes()))
        else:
            shutil.copy2(plain, target)

    target.chmod(0o600)
    offsite_path = None
    offsite_dir = os.getenv("STAFF_PAYROLL_OFFSITE_BACKUP_DIR", "").strip()
    if offsite_dir:
        offsite = Path(offsite_dir).expanduser()
        offsite.mkdir(parents=True, exist_ok=True)
        offsite_target = offsite / target.name
        shutil.copy2(target, offsite_target)
        offsite_target.chmod(0o600)
        offsite_path = str(offsite_target)

    keep = max(3, int(os.getenv("STAFF_PAYROLL_BACKUP_RETENTION", "30")))
    backups = sorted(
        directory.glob("staff-payroll-*.sqlite*"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        old.unlink(missing_ok=True)

    return {
        "name": target.name,
        "path": str(target),
        "bytes": target.stat().st_size,
        "encrypted": bool(secret),
        "offsite_path": offsite_path,
        "created_at": datetime.fromtimestamp(target.stat().st_mtime).replace(microsecond=0).isoformat(sep=" "),
    }


def _referenced_attachment_paths(db_path: Path) -> tuple[list[Path], list[str]]:
    if not db_path.exists():
        return [], []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    paths: list[Path] = []
    missing: list[str] = []
    try:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shift_change_requests'"
        ).fetchone()
        if not table_exists:
            return [], []
        rows = conn.execute(
            "SELECT attachment_path FROM shift_change_requests WHERE attachment_path IS NOT NULL AND attachment_path != ''"
        ).fetchall()
        for row in rows:
            path = Path(str(row["attachment_path"])).expanduser()
            if path.exists() and path.is_file():
                paths.append(path)
            else:
                missing.append(str(path))
    finally:
        conn.close()
    unique: dict[str, Path] = {str(path.resolve()): path for path in paths}
    return list(unique.values()), missing


def _safe_archive_name(path: Path, used: set[str]) -> str:
    try:
        upload_root = Path(os.getenv("STAFF_UPLOAD_DIR", "data/staff_uploads")).expanduser().resolve()
        resolved = path.resolve()
        if resolved.is_relative_to(upload_root):
            name = Path("uploads") / resolved.relative_to(upload_root)
        else:
            name = Path("uploads") / path.name
    except Exception:
        name = Path("uploads") / path.name
    candidate = str(name).replace("\\", "/")
    if candidate not in used:
        used.add(candidate)
        return candidate
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    parent = str(Path(candidate).parent).replace("\\", "/")
    index = 2
    while True:
        deduped = f"{parent}/{stem}-{index}{suffix}" if parent != "." else f"{stem}-{index}{suffix}"
        if deduped not in used:
            used.add(deduped)
            return deduped
        index += 1


def create_backup_package(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Create a ZIP backup containing a consistent SQLite copy plus uploaded staff documents."""
    source = Path(db_path).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")

    directory = backup_directory()
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = directory / f"staff-payroll-package-{timestamp}.zip"

    with tempfile.TemporaryDirectory(prefix="staff-payroll-package-") as temp_dir:
        plain = Path(temp_dir) / "staff-payroll.sqlite"
        _plain_backup(source, plain)
        attachments, missing = _referenced_attachment_paths(source)
        manifest = {
            "generated_at": datetime.now().replace(microsecond=0).isoformat(sep=" "),
            "db_name": source.name,
            "database_archive_path": "database/staff-payroll.sqlite",
            "attachment_count": len(attachments),
            "missing_attachment_paths": missing,
        }
        used_names = {"database/staff-payroll.sqlite", "manifest.json"}
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(plain, "database/staff-payroll.sqlite")
            for attachment in attachments:
                archive.write(attachment, _safe_archive_name(attachment, used_names))
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

    target.chmod(0o600)
    return {
        "name": target.name,
        "path": str(target),
        "bytes": target.stat().st_size,
        "encrypted": False,
        "attachment_count": len(attachments),
        "missing_attachment_paths": missing,
        "created_at": datetime.fromtimestamp(target.stat().st_mtime).replace(microsecond=0).isoformat(sep=" "),
    }


def verify_backup(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError("Backup not found.")
    encrypted = path.name.endswith(".fernet")
    with tempfile.TemporaryDirectory(prefix="staff-payroll-verify-") as temp_dir:
        candidate = Path(temp_dir) / "verify.sqlite"
        if encrypted:
            secret = os.getenv("STAFF_PAYROLL_BACKUP_KEY", "").strip()
            if not secret:
                raise RuntimeError("STAFF_PAYROLL_BACKUP_KEY is required to verify this backup.")
            try:
                decrypted = _fernet(secret).decrypt(path.read_bytes())
            except Exception as exc:
                raise RuntimeError("Backup decryption failed. Check the backup key.") from exc
            candidate.write_bytes(decrypted)
        else:
            shutil.copy2(path, candidate)
        _verify_sqlite(candidate)
        conn = sqlite3.connect(str(candidate))
        try:
            table_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
            )
        finally:
            conn.close()
    return {"ok": True, "name": path.name, "encrypted": encrypted, "table_count": table_count}


def list_backups() -> list[dict[str, Any]]:
    directory = backup_directory()
    if not directory.exists():
        return []
    return [
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "encrypted": path.name.endswith(".fernet"),
            "created_at": datetime.fromtimestamp(path.stat().st_mtime).replace(microsecond=0).isoformat(sep=" "),
        }
        for path in sorted(
            [*directory.glob("staff-payroll-*.sqlite*"), *directory.glob("staff-payroll-package-*.zip")],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    ]


def backup_path(name: str) -> Path:
    safe_name = Path(name).name
    if safe_name != name or not (safe_name.startswith("staff-payroll-") or safe_name.startswith("staff-payroll-package-")):
        raise ValueError("Invalid backup name.")
    return backup_directory() / safe_name
