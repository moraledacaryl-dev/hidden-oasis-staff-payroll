from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.security import current_user_from_token, require_api_key, role_to_key
from core.mfa_security import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_recovery_codes,
    hash_recovery_codes,
)

from core.audit import log_audit
from core.auth import (
    generate_totp_secret,
    hash_password,
    set_user_password,
    totp_setup_uri,
    verify_password,
    verify_totp,
)
from core.db import DB_PATH, fetchall, fetchone, get_conn, now_iso

router = APIRouter(prefix="/api/v1")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12)


class ToggleUserActiveRequest(BaseModel):
    active: bool


class LinkUserEmployeeRequest(BaseModel):
    employee_id: int | None = None


class CreateUserRequest(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=120)
    role: str = Field(default="Staff", min_length=2, max_length=40)
    employee_id: int | None = None


class ChangeUserRoleRequest(BaseModel):
    role: str


class MfaCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class DisableMfaRequest(MfaCodeRequest):
    password: str = Field(..., min_length=1)


def require_user(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    return current_user_from_token(authorization)


def require_owner(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    user = require_user(authorization, x_api_key)
    if user.get("role_key") != "owner":
        raise HTTPException(status_code=403, detail="Owner access required.")
    return user


def public_app_user(row: dict[str, Any]) -> dict[str, Any]:
    role_key = role_to_key(row.get("role"))
    return {
        "id": row.get("id"),
        "display_name": row.get("display_name") or "",
        "role": "General Manager" if role_key == "supervisor" else row.get("role") or "Staff",
        "role_key": role_key,
        "active": int(row.get("active") or 0),
        "must_change_password": int(row.get("must_change_password") or 0),
        "mfa_enabled": int(row.get("mfa_enabled") or 0),
        "last_login_at": row.get("last_login_at"),
        "created_at": row.get("created_at"),
        "employee_id": row.get("employee_id"),
        "employee_name": row.get("employee_name"),
    }


def normalized_role(value: str) -> tuple[str, str]:
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "owner": ("owner", "Owner"),
        "admin": ("owner", "Owner"),
        "administrator": ("owner", "Owner"),
        "payroll": ("payroll", "Payroll"),
        "payroll_admin": ("payroll", "Payroll"),
        "supervisor": ("supervisor", "General Manager"),
        "manager": ("supervisor", "General Manager"),
        "general_manager": ("supervisor", "General Manager"),
        "staff": ("staff", "Staff"),
        "employee": ("staff", "Staff"),
    }
    result = aliases.get(key)
    if not result:
        raise HTTPException(status_code=422, detail="Invalid role.")
    return result


def active_owner_count(conn) -> int:
    rows = fetchall(conn, "SELECT role FROM app_users WHERE active=1")
    return sum(1 for row in rows if role_to_key(row.get("role")) == "owner")


@router.post("/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        row = fetchone(conn, "SELECT * FROM app_users WHERE id=? AND active=1", (user.get("id"),))
        if not row:
            raise HTTPException(status_code=401, detail="User no longer exists or is inactive.")
        if not verify_password(payload.current_password, row.get("password_hash")):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        if len(payload.new_password) < 12:
            raise HTTPException(status_code=422, detail="Use at least 12 characters.")
        if verify_password(payload.new_password, row.get("password_hash")):
            raise HTTPException(status_code=422, detail="New password must be different.")
        set_user_password(conn, int(row["id"]), payload.new_password, must_change=False, commit=False)
        conn.execute(
            "UPDATE app_users SET last_login_at=COALESCE(last_login_at, ?), session_version=COALESCE(session_version,1)+1 WHERE id=?",
            (now_iso(), row["id"]),
        )
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="Password changed",
            table_name="app_users",
            record_id=int(row["id"]),
        )
        conn.commit()
        return {"ok": True, "message": "Password changed. Sign in again."}
    finally:
        conn.close()


@router.get("/users")
def list_users(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_owner(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        rows = fetchall(
            conn,
            """
            SELECT au.id, au.display_name, au.role, au.active, au.must_change_password,
                   au.mfa_enabled, au.last_login_at, au.created_at, au.employee_id,
                   e.full_name AS employee_name
            FROM app_users au
            LEFT JOIN employees e ON e.id = au.employee_id
            ORDER BY au.active DESC, au.role, au.display_name
            """,
        )
        return {"ok": True, "items": [public_app_user(row) for row in rows]}
    finally:
        conn.close()


@router.post("/users")
def create_user(
    payload: CreateUserRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    owner = require_owner(authorization, x_api_key)
    display_name = " ".join(payload.display_name.strip().split())
    _role_key, role_name = normalized_role(payload.role)
    temporary_password = f"HO-{secrets.token_urlsafe(12)}"
    conn = get_conn(DB_PATH)
    try:
        if fetchone(conn, "SELECT id FROM app_users WHERE lower(display_name)=lower(?)", (display_name,)):
            raise HTTPException(status_code=409, detail="That login name is already in use.")
        if payload.employee_id is not None:
            if not fetchone(conn, "SELECT id FROM employees WHERE id=?", (payload.employee_id,)):
                raise HTTPException(status_code=404, detail="Employee not found.")
            if fetchone(conn, "SELECT id FROM app_users WHERE employee_id=?", (payload.employee_id,)):
                raise HTTPException(status_code=409, detail="That employee already has an account.")
        cursor = conn.execute(
            """
            INSERT INTO app_users(
                display_name, role, password_hash, active, must_change_password,
                session_version, mfa_enabled, created_at, employee_id
            ) VALUES(?,?,?,1,1,1,0,?,?)
            """,
            (
                display_name,
                role_name,
                hash_password(temporary_password),
                now_iso(),
                payload.employee_id,
            ),
        )
        user_id = int(cursor.lastrowid)
        log_audit(
            conn,
            actor=owner.get("display_name"),
            action="User created",
            table_name="app_users",
            record_id=user_id,
            details={"role": role_name, "employee_id": payload.employee_id},
        )
        conn.commit()
        row = fetchone(conn, "SELECT * FROM app_users WHERE id=?", (user_id,)) or {}
        return {
            "ok": True,
            "user": public_app_user(row),
            "temporary_password": temporary_password,
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    owner = require_owner(authorization, x_api_key)
    temporary_password = f"HO-{secrets.token_urlsafe(9)}"
    conn = get_conn(DB_PATH)
    try:
        row = fetchone(conn, "SELECT * FROM app_users WHERE id=?", (user_id,))
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        set_user_password(conn, user_id, temporary_password, must_change=True, commit=False)
        conn.execute(
            "UPDATE app_users SET session_version=COALESCE(session_version,1)+1 WHERE id=?",
            (user_id,),
        )
        log_audit(
            conn,
            actor=owner.get("display_name"),
            action="Password reset",
            table_name="app_users",
            record_id=user_id,
        )
        conn.commit()
        return {
            "ok": True,
            "temporary_password": temporary_password,
            "user": public_app_user({**row, "must_change_password": 1}),
            "message": "Temporary password generated.",
        }
    finally:
        conn.close()


@router.post("/users/{user_id}/active")
def set_user_active(
    user_id: int,
    payload: ToggleUserActiveRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    owner = require_owner(authorization, x_api_key)
    if int(owner.get("id") or 0) == user_id and not payload.active:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own signed-in owner account.")
    conn = get_conn(DB_PATH)
    try:
        row = fetchone(conn, "SELECT * FROM app_users WHERE id=?", (user_id,))
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        if (
            not payload.active
            and role_to_key(row.get("role")) == "owner"
            and active_owner_count(conn) <= 1
        ):
            raise HTTPException(status_code=409, detail="At least one active owner account is required.")
        conn.execute(
            "UPDATE app_users SET active=?, session_version=COALESCE(session_version,1)+1 WHERE id=?",
            (1 if payload.active else 0, user_id),
        )
        log_audit(
            conn,
            actor=owner.get("display_name"),
            action="User activated" if payload.active else "User deactivated",
            table_name="app_users",
            record_id=user_id,
        )
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM app_users WHERE id=?", (user_id,)) or {}
        return {"ok": True, "user": public_app_user(updated)}
    finally:
        conn.close()


@router.post("/users/{user_id}/employee")
def set_user_employee(
    user_id: int,
    payload: LinkUserEmployeeRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    owner = require_owner(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        row = fetchone(conn, "SELECT * FROM app_users WHERE id=?", (user_id,))
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        employee_id = payload.employee_id
        if employee_id is not None:
            employee = fetchone(conn, "SELECT id FROM employees WHERE id=?", (employee_id,))
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found.")
            duplicate = fetchone(
                conn,
                "SELECT id FROM app_users WHERE employee_id=? AND id<>?",
                (employee_id, user_id),
            )
            if duplicate:
                raise HTTPException(status_code=409, detail="That employee already has an account.")
        conn.execute("UPDATE app_users SET employee_id=? WHERE id=?", (employee_id, user_id))
        log_audit(
            conn,
            actor=owner.get("display_name"),
            action="Employee account link changed",
            table_name="app_users",
            record_id=user_id,
            details={"employee_id": employee_id},
        )
        conn.commit()
        updated = fetchone(
            conn,
            """
            SELECT au.id, au.display_name, au.role, au.active, au.must_change_password,
                   au.last_login_at, au.created_at, au.employee_id,
                   e.full_name AS employee_name
            FROM app_users au
            LEFT JOIN employees e ON e.id = au.employee_id
            WHERE au.id=?
            """,
            (user_id,),
        ) or {}
        return {"ok": True, "user": public_app_user(updated)}
    finally:
        conn.close()


@router.post("/users/{user_id}/role")
def set_user_role(
    user_id: int,
    payload: ChangeUserRoleRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    owner = require_owner(authorization, x_api_key)
    _role_key, role = normalized_role(payload.role)
    conn = get_conn(DB_PATH)
    try:
        row = fetchone(conn, "SELECT * FROM app_users WHERE id=?", (user_id,))
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        if int(owner.get("id") or 0) == user_id and _role_key != "owner":
            raise HTTPException(status_code=409, detail="You cannot change your own owner role.")
        if (
            role_to_key(row.get("role")) == "owner"
            and _role_key != "owner"
            and int(row.get("active") or 0)
            and active_owner_count(conn) <= 1
        ):
            raise HTTPException(status_code=409, detail="At least one active owner account is required.")
        conn.execute(
            "UPDATE app_users SET role=?, session_version=COALESCE(session_version,1)+1 WHERE id=?",
            (role, user_id),
        )
        log_audit(
            conn,
            actor=owner.get("display_name"),
            action="User role changed",
            table_name="app_users",
            record_id=user_id,
            details={"old_role": row.get("role"), "new_role": role},
        )
        conn.commit()
        updated = fetchone(conn, "SELECT * FROM app_users WHERE id=?", (user_id,)) or {}
        return {"ok": True, "user": public_app_user(updated)}
    finally:
        conn.close()


@router.post("/auth/mfa/setup")
def setup_mfa(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_user(authorization, x_api_key)
    secret = generate_totp_secret()
    conn = get_conn(DB_PATH)
    try:
        conn.execute(
            """
            UPDATE app_users
            SET mfa_secret=?,
                mfa_enabled=0,
                mfa_confirmed_at=NULL,
                mfa_recovery_codes=NULL
            WHERE id=?
            """,
            (
                encrypt_mfa_secret(secret),
                user["id"],
            ),
        )
        conn.commit()
        return {
            "ok": True,
            "secret": secret,
            "otpauth_uri": totp_setup_uri(secret, str(user.get("display_name") or "User")),
        }
    finally:
        conn.close()


@router.post("/auth/mfa/confirm")
def confirm_mfa(
    payload: MfaCodeRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        row = fetchone(
            conn,
            "SELECT * FROM app_users WHERE id=? AND active=1",
            (user["id"],),
        )

        secret = (
            decrypt_mfa_secret(row.get("mfa_secret"))
            if row
            else None
        )

        if not row or not verify_totp(secret, payload.code):
            raise HTTPException(
                status_code=400,
                detail="Authenticator code is invalid.",
            )

        recovery_codes = generate_recovery_codes()

        conn.execute(
            """
            UPDATE app_users
            SET mfa_enabled=1,
                mfa_confirmed_at=?,
                mfa_recovery_codes=?,
                session_version=COALESCE(session_version,1)+1
            WHERE id=?
            """,
            (
                now_iso(),
                __import__("json").dumps(
                    hash_recovery_codes(recovery_codes)
                ),
                user["id"],
            ),
        )
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="MFA enabled",
            table_name="app_users",
            record_id=int(user["id"]),
        )
        conn.commit()
        return {
            "ok": True,
            "message": "Authenticator enabled. Save the recovery codes and sign in again.",
            "recovery_codes": recovery_codes,
        }
    finally:
        conn.close()


@router.post("/auth/mfa/disable")
def disable_mfa(
    payload: DisableMfaRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    user = require_user(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        row = fetchone(conn, "SELECT * FROM app_users WHERE id=? AND active=1", (user["id"],))
        if not row or not verify_password(payload.password, row.get("password_hash")):
            raise HTTPException(status_code=400, detail="Password is incorrect.")
        secret = decrypt_mfa_secret(row.get("mfa_secret"))

        if not verify_totp(secret, payload.code):
            raise HTTPException(
                status_code=400,
                detail="Authenticator code is invalid.",
            )
        conn.execute(
            """
            UPDATE app_users
            SET mfa_secret=NULL,
                mfa_enabled=0,
                mfa_confirmed_at=NULL,
                mfa_recovery_codes=NULL,
                session_version=COALESCE(session_version,1)+1
            WHERE id=?
            """,
            (user["id"],),
        )
        log_audit(
            conn,
            actor=user.get("display_name"),
            action="MFA disabled",
            table_name="app_users",
            record_id=int(user["id"]),
        )
        conn.commit()
        return {"ok": True, "message": "Authenticator disabled. Sign in again."}
    finally:
        conn.close()
