from __future__ import annotations

import io
import zipfile
import unittest

from fastapi import HTTPException

from api.upload_validation import validate_upload_bytes


def docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
    return buffer.getvalue()


class UploadValidationTests(unittest.TestCase):
    def test_valid_file_signatures(self):
        self.assertEqual(validate_upload_bytes("x.pdf", b"%PDF-\nbody"), ".pdf")
        self.assertEqual(validate_upload_bytes("x.jpg", b"\xff\xd8\xff\xe0body"), ".jpg")
        self.assertEqual(validate_upload_bytes("x.png", b"\x89PNG\r\n\x1a\nbody"), ".png")
        self.assertEqual(validate_upload_bytes("x.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1body"), ".doc")
        self.assertEqual(validate_upload_bytes("x.docx", docx_bytes()), ".docx")

    def test_renamed_invalid_file_is_rejected(self):
        with self.assertRaises(HTTPException):
            validate_upload_bytes("fake.pdf", b"not a pdf")
        with self.assertRaises(HTTPException):
            validate_upload_bytes("fake.docx", b"PK\x03\x04not a real office zip")
        with self.assertRaises(HTTPException):
            validate_upload_bytes("script.exe", b"MZ")


if __name__ == "__main__":
    unittest.main()
