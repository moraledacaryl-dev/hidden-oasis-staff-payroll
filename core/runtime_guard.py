from __future__ import annotations

import os


def enabled() -> bool:
    return os.getenv("STAFF_PAYROLL_ENV", "").strip().lower() in {"prod", "production"}


def validate_runtime_environment() -> None:
    if not enabled():
        return
    required = ["STAFF_PAYROLL_" + "API_KEY", "STAFF_PAYROLL_" + "SESSION_SECRET"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required runtime environment variables: " + ", ".join(missing))
