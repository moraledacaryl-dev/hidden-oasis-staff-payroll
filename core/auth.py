from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from typing import Any

from .db import fetchone, now_iso

PBKDF2_ITERATIONS = 260_000
DEFAULT_TEMP_PASSWORD = "ChangeMe123!"


def hash_password(password: str, salt: str | None = None) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not password or not stored_hash:
        return False
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)).hex()
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def set_user_password(conn: sqlite3.Connection, user_id: int, password: str, must_change: bool = False) -> None:
    conn.execute(
        "UPDATE app_users SET password_hash=?, must_change_password=? WHERE id=?",
        (hash_password(password), int(must_change), user_id),
    )
    conn.commit()


def bootstrap_missing_passwords(conn: sqlite3.Connection, temporary_password: str = DEFAULT_TEMP_PASSWORD) -> int:
    rows = conn.execute("SELECT id FROM app_users WHERE active=1 AND (password_hash IS NULL OR password_hash='')").fetchall()
    for row in rows:
        set_user_password(conn, int(row[0]), temporary_password, must_change=True)
    return len(rows)


def authenticate_user(conn: sqlite3.Connection, display_name: str, password: str) -> dict[str, Any] | None:
    user = fetchone(conn, "SELECT * FROM app_users WHERE display_name=? AND active=1", (display_name,))
    if not user or not verify_password(password, user.get("password_hash")):
        return None
    conn.execute("UPDATE app_users SET last_login_at=? WHERE id=?", (now_iso(), user["id"]))
    conn.commit()
    user["last_login_at"] = now_iso()
    return user


def role_in(role: str, allowed_roles: set[str] | tuple[str, ...]) -> bool:
    return role in set(allowed_roles)
