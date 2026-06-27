from __future__ import annotations

import zipfile
from pathlib import Path

from fastapi import HTTPException

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PDF_MAGIC = b"%PDF-"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
DOC_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"


def upload_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload PDF, JPG, PNG, DOC, or DOCX only.")
    return suffix


def validate_upload_bytes(filename: str | None, data: bytes) -> str:
    suffix = upload_suffix(filename)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit.")
    if suffix == ".pdf" and data.startswith(PDF_MAGIC):
        return suffix
    if suffix in {".jpg", ".jpeg"} and data.startswith(JPEG_MAGIC):
        return suffix
    if suffix == ".png" and data.startswith(PNG_MAGIC):
        return suffix
    if suffix == ".doc" and data.startswith(DOC_MAGIC):
        return suffix
    if suffix == ".docx":
        if not data.startswith(ZIP_MAGIC):
            raise HTTPException(status_code=400, detail="DOCX file content does not match its extension.")
        try:
            from io import BytesIO
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="DOCX file is not a valid Office document.") from exc
        if "[Content_Types].xml" in names and any(name.startswith("word/") for name in names):
            return suffix
    raise HTTPException(status_code=400, detail="Uploaded file content does not match its extension.")
