from __future__ import annotations

"""Stable authentication and authorization boundary.

This module is the canonical import surface for session, role, and API-key
security primitives. The implementation is temporarily delegated to
``api.main`` while the large legacy module is decomposed incrementally.
Consumers should import these names from here instead of depending directly
on the monolithic API module.
"""

from api.main import (
    IMPERSONATION_TTL_SECONDS,
    ROLE_OWNER,
    ROLE_PAYROLL,
    ROLE_STAFF,
    ROLE_SUPERVISOR,
    SESSION_TTL_SECONDS,
    b64url_decode,
    b64url_encode,
    current_user_from_token,
    public_user,
    require_api_key,
    require_authenticated_user,
    require_roles,
    role_to_key,
    session_users_from_payload,
    sign_payload,
    token_secret,
    verify_token,
)

__all__ = [
    "IMPERSONATION_TTL_SECONDS",
    "ROLE_OWNER",
    "ROLE_PAYROLL",
    "ROLE_STAFF",
    "ROLE_SUPERVISOR",
    "SESSION_TTL_SECONDS",
    "b64url_decode",
    "b64url_encode",
    "current_user_from_token",
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
