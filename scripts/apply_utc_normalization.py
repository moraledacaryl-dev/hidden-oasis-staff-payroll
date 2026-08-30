from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str, *, minimum: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count < minimum:
        raise RuntimeError(f"{path}: expected at least {minimum} matches, found {count}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Central time primitives: UTC for persisted instants; Asia/Manila for business dates.
replace_once(
    "core/observability.py",
    "from datetime import datetime, timezone\nfrom uuid import uuid4\n",
    "from datetime import date, datetime, timezone\nfrom uuid import uuid4\nfrom zoneinfo import ZoneInfo\n",
)
replace_once(
    "core/observability.py",
    '_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")\n',
    '_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")\nMANILA_TZ = ZoneInfo("Asia/Manila")\n',
)
replace_once(
    "core/observability.py",
    "def utc_iso(value: datetime | None = None) -> str:\n",
    "def utc_storage_iso(value: datetime | None = None) -> str:\n"
    "    \"\"\"Serialize an instant for SQLite text storage with an explicit UTC offset.\"\"\"\n"
    "    current = value or utc_now()\n"
    "    if current.tzinfo is None:\n"
    "        current = current.replace(tzinfo=timezone.utc)\n"
    "    return current.astimezone(timezone.utc).replace(microsecond=0).isoformat(sep=\" \")\n\n\n"
    "def manila_now(value: datetime | None = None) -> datetime:\n"
    "    \"\"\"Return an aware Asia/Manila datetime for business-calendar decisions.\"\"\"\n"
    "    current = value or utc_now()\n"
    "    if current.tzinfo is None:\n"
    "        current = current.replace(tzinfo=timezone.utc)\n"
    "    return current.astimezone(MANILA_TZ)\n\n\n"
    "def manila_today(value: datetime | None = None) -> date:\n"
    "    \"\"\"Return the Hidden Oasis business date in Asia/Manila.\"\"\"\n"
    "    return manila_now(value).date()\n\n\n"
    "def utc_iso(value: datetime | None = None) -> str:\n",
)

# Make the ubiquitous DB timestamp writer aware UTC without changing callers.
replace_once(
    "core/db.py",
    "from datetime import datetime\nfrom typing import Any, Callable, Iterable\n",
    "from typing import Any, Callable, Iterable\n\nfrom .observability import utc_storage_iso\n",
)
replace_once(
    "core/db.py",
    'def now_iso() -> str:\n    return datetime.now().replace(microsecond=0).isoformat(sep=" ")\n',
    'def now_iso() -> str:\n    return utc_storage_iso()\n',
)

# Login throttling must compare legacy-naive and new aware values as UTC instants.
replace_once(
    "core/login_security.py",
    "from datetime import datetime, timedelta\n\nfrom .db import fetchone, now_iso\n",
    "from datetime import timedelta\n\nfrom .db import fetchone, now_iso\nfrom .observability import parse_timestamp_utc, utc_now, utc_storage_iso\n",
)
replace_once(
    "core/login_security.py",
    '    try:\n        locked_until = datetime.fromisoformat(str(row["locked_until"]))\n    except ValueError:\n        return 0\n    return max(0, int((locked_until - datetime.now()).total_seconds()))\n',
    '    try:\n        locked_until = parse_timestamp_utc(str(row["locked_until"]))\n    except ValueError:\n        return 0\n    return max(0, int((locked_until - utc_now()).total_seconds()))\n',
)
replace_once(
    "core/login_security.py",
    '        (datetime.now() + timedelta(seconds=lock_seconds)).replace(microsecond=0).isoformat(sep=" ")\n',
    '        utc_storage_iso(utc_now() + timedelta(seconds=lock_seconds))\n',
)

# Outbox retries are operational instants; keep all retry scheduling in UTC.
replace_once(
    "core/integration_outbox.py",
    "from datetime import datetime, timedelta\nfrom typing import Any\n\nfrom core.db import fetchall, fetchone, now_iso\n",
    "from datetime import timedelta\nfrom typing import Any\n\nfrom core.db import fetchall, fetchone, now_iso\nfrom core.observability import utc_now, utc_storage_iso\n",
)
replace_all(
    "core/integration_outbox.py",
    '(datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat(sep=" ")',
    'utc_storage_iso(utc_now() + timedelta(hours=1))',
)
replace_all(
    "core/integration_outbox.py",
    '(datetime.now() + timedelta(seconds=_backoff_seconds(attempt))).replace(microsecond=0).isoformat(sep=" ")',
    'utc_storage_iso(utc_now() + timedelta(seconds=_backoff_seconds(attempt)))',
)

# Backup names and metadata represent instants, not local business dates.
replace_once(
    "core/backups.py",
    "from datetime import datetime\nfrom pathlib import Path\n",
    "from datetime import datetime, timezone\nfrom pathlib import Path\n",
)
replace_once(
    "core/backups.py",
    "from .offsite_backups import copy_offsite\n",
    "from .offsite_backups import copy_offsite\nfrom .observability import utc_iso, utc_now\n",
)
replace_all(
    "core/backups.py",
    'datetime.now().strftime("%Y%m%d-%H%M%S-%f")',
    'utc_now().strftime("%Y%m%d-%H%M%S-%fZ")',
    minimum=2,
)
replace_all(
    "core/backups.py",
    'datetime.fromtimestamp(target.stat().st_mtime).replace(microsecond=0).isoformat(sep=" ")',
    'utc_iso(datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc))',
    minimum=2,
)
replace_once(
    "core/backups.py",
    '"generated_at": datetime.now().replace(microsecond=0).isoformat(sep=" "),',
    '"generated_at": utc_iso(),',
)
replace_once(
    "core/backups.py",
    'datetime.fromtimestamp(path.stat().st_mtime).replace(microsecond=0).isoformat(sep=" ")',
    'utc_iso(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))',
)

# API: use central aware UTC writer and normalize *_at timestamp strings at the boundary.
replace_once(
    "api/main.py",
    "from core.db import DB_PATH, fetchall, fetchone, get_conn\n",
    "from core.db import DB_PATH, fetchall, fetchone, get_conn, now_iso\nfrom core.observability import parse_timestamp_utc, utc_iso\n",
)
replace_once(
    "api/main.py",
    '\n\ndef now_iso() -> str:\n    return datetime.now().replace(microsecond=0).isoformat(sep=" ")\n',
    '\n',
)
replace_once(
    "api/main.py",
    'def clean_row(row: dict[str, Any]) -> dict[str, Any]:\n    return {key: iso_value(value) for key, value in row.items()}\n',
    'def normalize_api_timestamp(value: Any) -> Any:\n'
    '    if not isinstance(value, str) or not value.strip():\n'
    '        return value\n'
    '    try:\n'
    '        return utc_iso(parse_timestamp_utc(value))\n'
    '    except ValueError:\n'
    '        return value\n\n'
    'def clean_row(row: dict[str, Any]) -> dict[str, Any]:\n'
    '    return {\n'
    '        key: normalize_api_timestamp(value) if key.endswith("_at") else iso_value(value)\n'
    '        for key, value in row.items()\n'
    '    }\n',
)

print("UTC normalization patch applied successfully.")
