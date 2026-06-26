from __future__ import annotations

import hashlib
import hmac
import base64
import secrets
import sqlite3
import struct
import time
from typing import Any
from urllib.parse import quote

from .db import fetchone, now_iso

PBKDF2_ITERATIONS = 260_000
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6


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


def set_user_password(
    conn: sqlite3.Connection,
    user_id: int,
    password: str,
    must_change: bool = False,
    *,
    commit: bool = True,
) -> None:
    conn.execute(
        "UPDATE app_users SET password_hash=?, must_change_password=? WHERE id=?",
        (hash_password(password), int(must_change), user_id),
    )
    if commit:
        conn.commit()


def provision_owner(
    conn: sqlite3.Connection,
    display_name: str,
    password: str,
    *,
    must_change: bool = True,
) -> int:
    clean_name = " ".join(display_name.strip().split())
    if len(clean_name) < 2:
        raise ValueError("Owner login name must contain at least 2 characters.")
    if len(password) < 12:
        raise ValueError("Owner password must contain at least 12 characters.")
    existing = fetchone(
        conn,
        "SELECT id FROM app_users WHERE lower(display_name)=lower(?)",
        (clean_name,),
    )
    if existing:
        user_id = int(existing["id"])
        conn.execute(
            """
            UPDATE app_users
            SET role='Owner', active=1, password_hash=?, must_change_password=?,
                session_version=COALESCE(session_version,1)+1
            WHERE id=?
            """,
            (hash_password(password), int(must_change), user_id),
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO app_users(
                display_name, role, password_hash, active, must_change_password,
                session_version, mfa_enabled, created_at
            ) VALUES(?, 'Owner', ?, 1, ?, 1, 0, ?)
            """,
            (clean_name, hash_password(password), int(must_change), now_iso()),
        )
        user_id = int(cursor.lastrowid)
    conn.commit()
    return user_id


def bootstrap_missing_passwords(conn: sqlite3.Connection) -> dict[int, str]:
    rows = conn.execute("SELECT id FROM app_users WHERE active=1 AND (password_hash IS NULL OR password_hash='')").fetchall()
    generated: dict[int, str] = {}
    for row in rows:
        password = f"HO-{secrets.token_urlsafe(12)}"
        set_user_password(conn, int(row[0]), password, must_change=True)
        generated[int(row[0])] = password
    return generated


def authenticate_user(
    conn: sqlite3.Connection,
    display_name: str,
    password: str,
    *,
    record_login: bool = True,
) -> dict[str, Any] | None:
    user = fetchone(
        conn,
        "SELECT * FROM app_users WHERE lower(display_name)=lower(?) AND active=1",
        (" ".join(display_name.strip().split()),),
    )
    if not user or not verify_password(password, user.get("password_hash")):
        return None
    if record_login:
        logged_in_at = now_iso()
        conn.execute("UPDATE app_users SET last_login_at=? WHERE id=?", (logged_in_at, user["id"]))
        conn.commit()
        user["last_login_at"] = logged_in_at
    return user


def role_in(role: str, allowed_roles: set[str] | tuple[str, ...]) -> bool:
    return role in set(allowed_roles)


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_code(secret: str, counter: int) -> str:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**TOTP_DIGITS)
    return str(value).zfill(TOTP_DIGITS)


def verify_totp(secret: str | None, code: str | None, at_time: int | None = None) -> bool:
    if not secret or not code or not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    counter = int(at_time or time.time()) // TOTP_STEP_SECONDS
    return any(
        hmac.compare_digest(_totp_code(secret, counter + offset), code)
        for offset in (-1, 0, 1)
    )


def totp_setup_uri(secret: str, display_name: str) -> str:
    issuer = "Hidden Oasis"
    label = quote(f"{issuer}:{display_name}")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&digits={TOTP_DIGITS}&period={TOTP_STEP_SECONDS}"
    )
