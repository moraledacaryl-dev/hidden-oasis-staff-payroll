from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    """Serialize an instant in a stable UTC ISO-8601 representation."""
    current = value or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (
        current.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_timestamp_utc(value: str) -> datetime:
    """Parse legacy-naive or timezone-aware ISO timestamps as UTC instants."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Timestamp is required.")
    normalized = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_request_id(value: str | None) -> str:
    """Reuse a safe caller correlation ID or generate a fresh opaque one."""
    candidate = str(value or "").strip()
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex
