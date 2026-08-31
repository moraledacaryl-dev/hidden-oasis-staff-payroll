from __future__ import annotations

import re
from datetime import date, datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MANILA_TZ = ZoneInfo("Asia/Manila")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    current = value or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (
        current.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def utc_storage_iso(value: datetime | None = None) -> str:
    """Serialize an aware UTC instant while preserving legacy SQL sort order.

    Existing SQLite rows use ``YYYY-MM-DD HH:MM:SS``. Keeping the same date/time
    prefix and adding ``+00:00`` means simple TEXT comparisons remain ordered
    across historical and new rows while new writes carry an explicit offset.
    """
    current = value or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).replace(microsecond=0).isoformat(sep=" ")


def parse_timestamp_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("Timestamp is required.")
        normalized = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(normalized)
    # Historical application and SQLite CURRENT_TIMESTAMP values were written
    # without an offset but represented UTC in production. Preserve that
    # interpretation so legacy rows remain comparable to new aware values.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def manila_now(value: datetime | None = None) -> datetime:
    current = value or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(MANILA_TZ)


def business_today(value: datetime | None = None) -> date:
    """Return the Hidden Oasis business date in Asia/Manila."""
    return manila_now(value).date()


def normalize_request_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex
