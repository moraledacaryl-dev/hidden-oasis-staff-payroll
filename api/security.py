from __future__ import annotations

"""Canonical authentication and authorization boundary.

This module owns session-token, role, API-key, and authenticated-user
primitives. It intentionally depends only on the database core and FastAPI,
not on the legacy ``api.main`` application module.
"""

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from fastapi import Depends, Header, HTTPException, status

from core.db import DB_PATH, fetchone, get_conn

SESSION_TTL_SECONDS = 12 * 60 * 60
IMPERSONATION_TTL_SECONDS = 30 * 60
ROLE_OWNER = "owner"
ROLE_PAYROLL = "payroll"
ROLE_SUPERVISOR = "supervisor"
ROLE_STAFF = "staff"


def configured_db_path() -> Path:
    return Path(os.getenv("STAFF_PAYROLL_DB_PATH", str(DB_PATH))).expanduser()


@contextmanager
def db_conn(read_only: bool = False) -> Iterator[Any]:
    db_path = configured_db_path()
    if read_only:
        if not db_path.exists():
            raise HTTPException(status_code=500, detail=f"Database not found: {db_path}")
        uri = f"file:{db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn = get_conn(db_path)
    try:
        yield conn
    finally:
        conn.close()


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = os.getenv("STAFF_PAYROLL_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


def role_to_key(role: str | None) -> str:
    text = (role or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"owner", "admin", "administrator"}:
        return ROLE_OWNER
    if text in {"payroll", "payroll_admin", "hr", "hr_payroll"}:
        return ROLE_PAYROLL
    if text in {"supervisor", "manager", "general_manager", "department_head"}:
        return ROLE_SUPERVISOR
    return ROLE_STAFF


def privileged_mfa_required(user: dict[str, Any]) -> bool:
    required = (
        os.getenv("STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA", "false")
        .strip()
        .lower()
        == "true"
    )
    if not required:
        return False

    role_key = role_to_key(user.get("role"))
    return (
        role_key in {ROLE_OWNER, ROLE_PAYROLL}
        and not int(user.get("mfa_enabled") or 0)
    )


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    role_key = role_to_key(user.get("role"))
    return {
        "id": user.get("id"),
        "display_name": user.get("display_name") or "",
        "role": (
            "General Manager"
            if role_key == ROLE_SUPERVISOR
            else user.get("role") or "Staff"
        ),
        "role_key": role_key,
        "active": int(user.get("active") or 0),
        "must_change_password": int(user.get("must_change_password") or 0),
        "mfa_enabled": int(user.get("mfa_enabled") or 0),
        "mfa_setup_required": int(
            privileged_mfa_required(user)
        ),
        "employee_id": user.get("employee_id"),
        "session_version": int(user.get("session_version") or 1),
        "last_login_at": user.get("last_login_at"),
    }


def token_secret() -> str:
    return (
        os.getenv("STAFF_PAYROLL_SESSION_SECRET")
        or os.getenv("STAFF_PAYROLL_API_KEY")
        or "dev-only-change-staff-payroll-session-secret"
    )


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_payload(payload: dict[str, Any]) -> str:
    body = b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        token_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{body}.{b64url_encode(signature)}"


def verify_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            token_secret().encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(b64url_decode(signature), expected):
            raise ValueError("bad signature")
        payload = json.loads(b64url_decode(body).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        ) from exc


def session_users_from_payload(
    conn: Any,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    user = fetchone(
        conn,
        "SELECT * FROM app_users WHERE id=? AND active=1",
        (payload.get("sub"),),
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists or is inactive.",
        )
    if int(payload.get("sv") or 1) != int(user.get("session_version") or 1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked.",
        )

    impersonator_id = payload.get("imp_by")
    if impersonator_id is None:
        return user, None

    impersonator = fetchone(
        conn,
        "SELECT * FROM app_users WHERE id=? AND active=1",
        (impersonator_id,),
    )
    if (
        not impersonator
        or int(impersonator.get("id") or 0) == int(user.get("id") or 0)
        or role_to_key(impersonator.get("role")) != ROLE_OWNER
        or int(payload.get("imp_sv") or 0)
        != int(impersonator.get("session_version") or 1)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner view session is no longer valid.",
        )
    return user, impersonator


def current_user_from_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    payload = verify_token(authorization.removeprefix("Bearer ").strip())
    with db_conn(read_only=True) as conn:
        user, impersonator = session_users_from_payload(conn, payload)
    result = public_user(user)
    if impersonator:
        result.update(
            {
                "is_impersonating": 1,
                "impersonator_id": int(impersonator["id"]),
                "impersonator_name": impersonator.get("display_name") or "Owner",
                "must_change_password": 0,
                "mfa_setup_required": 0,
            }
        )
    return result


def require_authenticated_user(
    user: dict[str, Any] = Depends(current_user_from_token),
) -> dict[str, Any]:
    if (
        not user.get("is_impersonating")
        and int(user.get("mfa_setup_required") or 0)
    ):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="MFA setup is required for this account.",
        )

    return user


def require_roles(
    *allowed_roles: str,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    allowed = {role_to_key(role) for role in allowed_roles}

    def _require_role(
        user: dict[str, Any] = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        if user.get("role_key") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "This action requires one of these roles: "
                    f"{', '.join(sorted(allowed))}."
                ),
            )
        return user

    return _require_role


__all__ = [
    "IMPERSONATION_TTL_SECONDS",
    "ROLE_OWNER",
    "ROLE_PAYROLL",
    "ROLE_STAFF",
    "ROLE_SUPERVISOR",
    "SESSION_TTL_SECONDS",
    "b64url_decode",
    "b64url_encode",
    "configured_db_path",
    "current_user_from_token",
    "db_conn",
    "privileged_mfa_required",
    "public_user",
    "require_api_key",
    "require_authenticated_user",
    "require_roles",
    "role_to_key",
    "session_users_from_payload",
    "sign_payload",
    "token_secret",
    "verify_token",
]
