from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Iterable


MFA_SECRET_PREFIX = "fernet:"
RECOVERY_CODE_COUNT = 10


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "cryptography is required for encrypted MFA secret storage."
        ) from exc

    secret = os.getenv("STAFF_PAYROLL_MFA_KEY", "").strip()

    if not secret:
        raise RuntimeError(
            "STAFF_PAYROLL_MFA_KEY must be configured."
        )

    key = base64.urlsafe_b64encode(
        hashlib.sha256(secret.encode("utf-8")).digest()
    )

    return Fernet(key)


def encrypt_mfa_secret(secret: str) -> str:
    if not secret:
        raise ValueError("MFA secret cannot be empty.")

    encrypted = _fernet().encrypt(secret.encode("utf-8")).decode("ascii")
    return MFA_SECRET_PREFIX + encrypted


def decrypt_mfa_secret(stored: str | None) -> str | None:
    if not stored:
        return None

    if not stored.startswith(MFA_SECRET_PREFIX):
        # Legacy plaintext compatibility for controlled migration.
        return stored

    token = stored.removeprefix(MFA_SECRET_PREFIX)

    return _fernet().decrypt(
        token.encode("ascii")
    ).decode("utf-8")


def generate_recovery_codes(
    count: int = RECOVERY_CODE_COUNT,
) -> list[str]:
    return [
        f"{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
        for _ in range(count)
    ]


def hash_recovery_code(code: str) -> str:
    clean = code.strip().upper()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def hash_recovery_codes(codes: Iterable[str]) -> list[str]:
    return [hash_recovery_code(code) for code in codes]
