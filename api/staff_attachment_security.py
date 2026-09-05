from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.security import current_user_from_token, require_api_key
from api.staff_self_service import audit, employee_for_user, ensure_schema, now_iso
from api.upload_validation import MAX_UPLOAD_BYTES, validate_upload_bytes
from core.db import DB_PATH, fetchone, get_conn

router = APIRouter(prefix="/api/v1")
PENDING_ATTACHMENT_STATUSES = {"Pending", "Swap Confirmation", "Emergency Review"}
REVIEWER_ROLES = {"owner", "payroll", "supervisor"}
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


def upload_root() -> Path:
    return Path(os.getenv("STAFF_UPLOAD_DIR", "data/staff_uploads")).expanduser().resolve()


def ensure_attachment_schema(conn) -> None:
    ensure_schema(conn)
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(shift_change_requests)")}
    additions = {
        "attachment_original_name": "TEXT",
        "attachment_sha256": "TEXT",
        "attachment_size_bytes": "INTEGER",
        "attachment_validation_status": "TEXT",
        "attachment_uploaded_at": "TEXT",
    }
    for name, column_type in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE shift_change_requests ADD COLUMN {name} {column_type}")
    conn.commit()


def _require_api_key(x_api_key: str | None) -> None:
    require_api_key(x_api_key)


def _safe_download_name(original: str | None, request_id: int, suffix: str) -> str:
    candidate = Path(str(original or "")).name.strip()
    candidate = _SAFE_FILENAME.sub("_", candidate).strip(" .")
    if not candidate:
        return f"shift-request-{request_id}{suffix}"
    if Path(candidate).suffix.lower() != suffix.lower():
        candidate = f"{Path(candidate).stem or f'shift-request-{request_id}'}{suffix}"
    return candidate[:180]


def _resolved_attachment_path(stored_path: str | None) -> Path:
    if not stored_path:
        raise HTTPException(status_code=404, detail="No attachment is stored for this request.")
    root = upload_root()
    path = Path(stored_path).expanduser().resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=409, detail="Stored attachment path is outside the managed upload area.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is unavailable.")
    return path


def _request_for_attachment(conn, request_id: int) -> dict[str, Any]:
    row = fetchone(conn, "SELECT * FROM shift_change_requests WHERE id=?", (request_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Request not found.")
    return row


def _authorize_download(conn, row: dict[str, Any], user: dict[str, Any]) -> int | None:
    role = str(user.get("role_key") or "").lower()
    if role in REVIEWER_ROLES:
        return None
    if role != "staff":
        raise HTTPException(status_code=403, detail="Attachment access is not permitted for this account.")
    employee = employee_for_user(conn, user)
    employee_id = int(employee["id"])
    if employee_id != int(row.get("employee_id") or 0):
        raise HTTPException(status_code=404, detail="Request not found.")
    return employee_id


def _download_response(conn, request_id: int, user: dict[str, Any]) -> FileResponse:
    row = _request_for_attachment(conn, request_id)
    actor_employee_id = _authorize_download(conn, row, user)
    status = str(row.get("attachment_validation_status") or "legacy").lower()
    if status not in {"validated", "legacy"}:
        raise HTTPException(status_code=409, detail="Attachment is not available for download.")
    path = _resolved_attachment_path(row.get("attachment_path"))
    suffix = path.suffix.lower()
    filename = _safe_download_name(row.get("attachment_original_name"), request_id, suffix)
    audit(conn, request_id, "Attachment Downloaded", int(user["id"]), actor_employee_id, filename)
    conn.commit()
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.post("/me/shift-change-requests/{request_id}/attachment")
def upload_shift_request_attachment(
    request_id: int,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _require_api_key(x_api_key)
    if str(user.get("role_key") or "").lower() != "staff":
        raise HTTPException(status_code=403, detail="Staff self-service account required.")

    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    suffix = validate_upload_bytes(file.filename, raw)
    digest = hashlib.sha256(raw).hexdigest()
    root = upload_root()
    quarantine = root / ".quarantine"

    conn = get_conn(DB_PATH)
    staged: Path | None = None
    final_path: Path | None = None
    try:
        row = _request_for_attachment(conn, request_id)
        employee = employee_for_user(conn, user)
        employee_id = int(employee["id"])
        if employee_id != int(row.get("employee_id") or 0):
            raise HTTPException(status_code=404, detail="Request not found.")
        if str(row.get("status") or "") not in PENDING_ATTACHMENT_STATUSES:
            raise HTTPException(status_code=409, detail="Attachments can only be changed while the request is pending review.")

        root.mkdir(parents=True, exist_ok=True)
        quarantine.mkdir(parents=True, exist_ok=True)
        quarantine.chmod(0o700)
        token = uuid.uuid4().hex
        staged = quarantine / f"{token}{suffix}"
        final_path = root / f"shift-request-{request_id}-{token}{suffix}"
        with staged.open("xb") as handle:
            handle.write(raw)
        staged.chmod(0o600)
        os.replace(staged, final_path)
        final_path.chmod(0o600)

        old_path = row.get("attachment_path")
        conn.execute(
            """
            UPDATE shift_change_requests
            SET attachment_path=?, attachment_original_name=?, attachment_sha256=?,
                attachment_size_bytes=?, attachment_validation_status='validated',
                attachment_uploaded_at=?
            WHERE id=?
            """,
            (
                str(final_path),
                Path(str(file.filename or "attachment")).name[:255],
                digest,
                len(raw),
                now_iso(),
                request_id,
            ),
        )
        audit(conn, request_id, "Attachment Uploaded", int(user["id"]), employee_id, f"sha256={digest}; size={len(raw)}")
        conn.commit()

        if old_path:
            try:
                old = _resolved_attachment_path(str(old_path))
                if old != final_path:
                    old.unlink(missing_ok=True)
            except HTTPException:
                pass

        return {
            "ok": True,
            "filename": Path(str(file.filename or "attachment")).name,
            "size_bytes": len(raw),
            "sha256": digest,
            "validation_status": "validated",
        }
    except Exception:
        conn.rollback()
        if staged is not None:
            staged.unlink(missing_ok=True)
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    finally:
        conn.close()


@router.get("/me/shift-change-requests/{request_id}/attachment")
def download_my_shift_request_attachment(
    request_id: int,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> FileResponse:
    _require_api_key(x_api_key)
    conn = get_conn(DB_PATH)
    try:
        return _download_response(conn, request_id, user)
    finally:
        conn.close()


@router.get("/shift-change-requests/{request_id}/attachment")
def download_shift_request_attachment_for_review(
    request_id: int,
    user: dict[str, Any] = Depends(current_user_from_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> FileResponse:
    _require_api_key(x_api_key)
    if str(user.get("role_key") or "").lower() not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Reviewer access required.")
    conn = get_conn(DB_PATH)
    try:
        return _download_response(conn, request_id, user)
    finally:
        conn.close()
