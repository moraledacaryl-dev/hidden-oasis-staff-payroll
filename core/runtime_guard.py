from __future__ import annotations

import os


PRODUCTION_SECRET_NAMES = (
    "STAFF_PAYROLL_API_KEY",
    "STAFF_PAYROLL_SESSION_SECRET",
    "STAFF_PAYROLL_MFA_KEY",
)
PLACEHOLDER_MARKERS = (
    "replace-with",
    "change-me",
    "changeme",
    "example",
    "default",
    "dev-only",
    "password",
    "secret123",
)


def enabled() -> bool:
    return os.getenv("STAFF_PAYROLL_ENV", "").strip().lower() in {"prod", "production"}


def _secret_problem(name: str, value: str | None) -> str | None:
    if value is None or value == "":
        return f"{name} is missing"
    if value != value.strip():
        return f"{name} has leading or trailing whitespace"
    if any(character.isspace() for character in value):
        return f"{name} contains whitespace"
    lowered = value.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return f"{name} still contains a placeholder/default value"
    if len(value.encode("utf-8")) < 32:
        return f"{name} must contain at least 32 bytes"
    if len(set(value)) < 12:
        return f"{name} does not have enough character diversity"
    return None


def validate_runtime_environment() -> None:
    if not enabled():
        return

    problems: list[str] = []
    values: dict[str, str] = {}
    for name in PRODUCTION_SECRET_NAMES:
        value = os.getenv(name)
        problem = _secret_problem(name, value)
        if problem:
            problems.append(problem)
        elif value is not None:
            values[name] = value

    if len(values) == len(PRODUCTION_SECRET_NAMES):
        if len(set(values.values())) != len(values):
            problems.append("API, session, and MFA secrets must all be independent values")

    privileged_mfa = (
        os.getenv("STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA", "")
        .strip()
        .lower()
    )
    if privileged_mfa != "true":
        problems.append(
            "STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA must be true in production"
        )

    if problems:
        raise RuntimeError(
            "Unsafe production runtime configuration: " + "; ".join(problems)
        )
