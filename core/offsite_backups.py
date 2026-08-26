from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


S3_ENV_NAMES = (
    "STAFF_PAYROLL_OFFSITE_S3_ENDPOINT",
    "STAFF_PAYROLL_OFFSITE_S3_BUCKET",
    "STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID",
    "STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _s3_config() -> dict[str, str] | None:
    values = {name: os.getenv(name, "").strip() for name in S3_ENV_NAMES}
    populated = [name for name, value in values.items() if value]
    if not populated:
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Incomplete S3 offsite backup configuration; missing: " + ", ".join(missing)
        )
    endpoint = values["STAFF_PAYROLL_OFFSITE_S3_ENDPOINT"].rstrip("/")
    if not endpoint.startswith("https://"):
        raise RuntimeError("STAFF_PAYROLL_OFFSITE_S3_ENDPOINT must use HTTPS")
    return {
        "endpoint": endpoint,
        "bucket": values["STAFF_PAYROLL_OFFSITE_S3_BUCKET"],
        "access_key": values["STAFF_PAYROLL_OFFSITE_S3_ACCESS_KEY_ID"],
        "secret_key": values["STAFF_PAYROLL_OFFSITE_S3_SECRET_ACCESS_KEY"],
        "region": os.getenv("STAFF_PAYROLL_OFFSITE_S3_REGION", "").strip() or "us-east-1",
        "prefix": os.getenv("STAFF_PAYROLL_OFFSITE_S3_PREFIX", "staff-payroll").strip().strip("/"),
    }


def s3_configured() -> bool:
    return _s3_config() is not None


def _s3_client(config: dict[str, str]):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for S3-compatible offsite backups"
        ) from exc
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        region_name=config["region"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
    )


def _object_key(config: dict[str, str], name: str) -> str:
    prefix = config.get("prefix", "").strip("/")
    return f"{prefix}/{name}" if prefix else name


def copy_offsite(target: Path) -> str | None:
    """Copy an encrypted/local backup to either a mounted directory or S3.

    A mounted-directory destination remains supported for installations with a
    genuinely separate filesystem. S3 is preferred where no remote filesystem
    is mounted.
    """
    offsite_dir = os.getenv("STAFF_PAYROLL_OFFSITE_BACKUP_DIR", "").strip()
    if offsite_dir:
        directory = Path(offsite_dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        offsite_target = directory / target.name
        shutil.copy2(target, offsite_target)
        offsite_target.chmod(0o600)
        return str(offsite_target)

    config = _s3_config()
    if config is None:
        return None
    client = _s3_client(config)
    key = _object_key(config, target.name)
    digest = sha256_file(target)
    client.upload_file(
        str(target),
        config["bucket"],
        key,
        ExtraArgs={
            "ContentType": "application/octet-stream",
            "Metadata": {
                "sha256": digest,
                "bytes": str(target.stat().st_size),
                "encrypted": "true" if target.name.endswith(".fernet") else "false",
            },
        },
    )
    return f"s3://{config['bucket']}/{key}"


def verify_offsite_copy(local_path: Path) -> dict[str, Any]:
    """Verify the configured offsite copy matches a local encrypted backup."""
    offsite_dir = os.getenv("STAFF_PAYROLL_OFFSITE_BACKUP_DIR", "").strip()
    if offsite_dir:
        candidate = Path(offsite_dir).expanduser() / local_path.name
        exists = candidate.is_file()
        matching = False
        if exists:
            matching = (
                candidate.stat().st_size == local_path.stat().st_size
                and sha256_file(candidate) == sha256_file(local_path)
            )
        return {
            "configured": True,
            "kind": "directory",
            "destination": str(candidate),
            "exists": exists,
            "matching": matching,
            "last_modified": (
                datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
                if exists
                else None
            ),
        }

    config = _s3_config()
    if config is None:
        return {
            "configured": False,
            "kind": None,
            "destination": None,
            "exists": False,
            "matching": False,
            "last_modified": None,
        }

    client = _s3_client(config)
    key = _object_key(config, local_path.name)
    destination = f"s3://{config['bucket']}/{key}"
    try:
        head = client.head_object(Bucket=config["bucket"], Key=key)
    except Exception as exc:
        response = getattr(exc, "response", None)
        status = None
        if isinstance(response, dict):
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return {
                "configured": True,
                "kind": "s3",
                "destination": destination,
                "exists": False,
                "matching": False,
                "last_modified": None,
            }
        raise

    metadata = {str(k).lower(): str(v) for k, v in (head.get("Metadata") or {}).items()}
    expected_sha = sha256_file(local_path)
    expected_size = local_path.stat().st_size
    size_ok = int(head.get("ContentLength", -1)) == expected_size
    sha_ok = metadata.get("sha256", "").lower() == expected_sha.lower()
    return {
        "configured": True,
        "kind": "s3",
        "destination": destination,
        "exists": True,
        "matching": bool(size_ok and sha_ok),
        "last_modified": head.get("LastModified"),
        "content_length": head.get("ContentLength"),
        "sha256": metadata.get("sha256"),
    }
