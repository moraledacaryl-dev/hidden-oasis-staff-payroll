from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile

from api.security import current_user_from_token, require_api_key
from api.staff_self_service import audit, employee_for_user, ensure_schema, now_iso
from api.upload_validation import MAX_UPLOAD_BYTES, validate_upload_bytes
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")
UPLOAD_DIR = Path(os.getenv("STAFF_UPLOAD_DIR", "data/staff_uploads"))


def require_staff_user(x_api_key: str | None, user: dict[str, Any]) -> dict[str, Any]:
    require_api_key(x_api_key)
    if user.get("role_key") != "staff":
        raise HTTPException(status_code=403, detail="Staff self-service account required.")
    return user


@router.post("/me/shift-change-requests/{request_id}/attachment")
def upload_shift_request_attachment(
    request_id: int,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    require_staff_user(x_api_key, user)
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    suffix = validate_upload_bytes(file.filename, raw)
    conn = get_conn(DB_PATH)
    try:
        ensure_schema(conn)
        employee = employee_for_user(conn, user)
        row = fetchone(conn, "SELECT * FROM shift_change_requests WHERE id=? AND employee_id=?", (request_id, employee["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Request not found.")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / f"shift-request-{request_id}-{now_iso().replace(':', '').replace(' ', '-')}{suffix}"
        target.write_bytes(raw)
        target.chmod(0o600)
        conn.execute("UPDATE shift_change_requests SET attachment_path=? WHERE id=?", (str(target), request_id))
        audit(conn, request_id, "Attachment Uploaded", int(user["id"]), int(employee["id"]), file.filename)
        conn.commit()
        return {"ok": True, "filename": file.filename}
    finally:
        conn.close()
