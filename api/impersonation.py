from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.main import (
    IMPERSONATION_TTL_SECONDS,
    current_user_from_token,
    public_user,
    require_api_key,
    role_to_key,
    sign_payload,
)
from core.audit import log_audit
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")


class StartImpersonationRequest(BaseModel):
    target_user_id: int = Field(..., gt=0)


class EndImpersonationRequest(BaseModel):
    target_user_id: int | None = Field(default=None, gt=0)


def require_owner(authorization: str | None, x_api_key: str | None) -> dict[str, Any]:
    require_api_key(x_api_key)
    user = current_user_from_token(authorization)
    if user.get("role_key") != "owner" or user.get("is_impersonating"):
        raise HTTPException(status_code=403, detail="Owner access required.")
    return user


@router.post("/auth/impersonate")
def start_impersonation(
    payload: StartImpersonationRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    owner = require_owner(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        target = fetchone(
            conn,
            """
            SELECT au.*, e.status AS employee_status
            FROM app_users au
            LEFT JOIN employees e ON e.id=au.employee_id
            WHERE au.id=? AND au.active=1
            """,
            (payload.target_user_id,),
        )
        if not target:
            raise HTTPException(status_code=404, detail="Active user not found.")
        target_role = role_to_key(target.get("role"))
        if target_role not in {"supervisor", "staff"}:
            raise HTTPException(status_code=422, detail="Only General Manager or staff accounts can be viewed.")
        employee_status = str(target.get("employee_status") or "").strip().lower()
        if target_role == "staff" and (
            not target.get("employee_id")
            or not employee_status
            or employee_status in {"inactive", "terminated"}
        ):
            raise HTTPException(status_code=409, detail="Choose a staff account linked to an active employee.")

        issued_at = int(time.time())
        expires_at = issued_at + IMPERSONATION_TTL_SECONDS
        token = sign_payload(
            {
                "sub": int(target["id"]),
                "role": target_role,
                "sv": int(target.get("session_version") or 1),
                "imp_by": int(owner["id"]),
                "imp_sv": int(owner.get("session_version") or 1),
                "iat": issued_at,
                "exp": expires_at,
            }
        )
        log_audit(
            conn,
            actor=owner.get("display_name"),
            action="Owner view started",
            table_name="app_users",
            record_id=int(target["id"]),
            details={"target": target.get("display_name"), "role": target_role, "mode": "act_as"},
        )
        conn.commit()
        viewed_user = public_user(target)
        viewed_user.update(
            {
                "is_impersonating": 1,
                "impersonator_id": int(owner["id"]),
                "impersonator_name": owner.get("display_name") or "Owner",
                "must_change_password": 0,
                "mfa_setup_required": 0,
            }
        )
        return {
            "ok": True,
            "access_token": token,
            "token_type": "bearer",
            "expires_in": IMPERSONATION_TTL_SECONDS,
            "user": viewed_user,
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/auth/impersonate/end")
def end_impersonation(
    payload: EndImpersonationRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    owner = require_owner(authorization, x_api_key)
    conn = get_conn(DB_PATH)
    try:
        target = (
            fetchone(conn, "SELECT display_name FROM app_users WHERE id=?", (payload.target_user_id,))
            if payload.target_user_id
            else None
        )
        log_audit(
            conn,
            actor=owner.get("display_name"),
            action="Owner view ended",
            table_name="app_users",
            record_id=payload.target_user_id,
            details={"target": target.get("display_name") if target else None},
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
