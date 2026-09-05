from __future__ import annotations

import unittest
from pathlib import Path

from api.staff_self_service import public_request_row


ROOT = Path(__file__).resolve().parents[1]


class StaffAttachmentPathRedactionTests(unittest.TestCase):
    def test_public_request_row_replaces_private_path_with_presence_flag(self) -> None:
        source = {
            "id": 42,
            "request_no": "SCR-42",
            "attachment_path": "/var/lib/hiddenoasis/staff-payroll/uploads/private-file.pdf",
        }

        public = public_request_row(source)

        self.assertNotIn("attachment_path", public)
        self.assertTrue(public["has_attachment"])
        self.assertEqual(source["attachment_path"], "/var/lib/hiddenoasis/staff-payroll/uploads/private-file.pdf")

    def test_public_request_row_reports_no_attachment_without_path(self) -> None:
        public = public_request_row({"id": 43, "attachment_path": None})

        self.assertNotIn("attachment_path", public)
        self.assertFalse(public["has_attachment"])

    def test_all_client_response_surfaces_use_redacted_dto(self) -> None:
        source = (ROOT / "api" / "staff_self_service.py").read_text(encoding="utf-8")

        self.assertIn('"requests": [public_request_row(item) for item in requests]', source)
        self.assertIn('"items": [public_request_row(item) for item in items]', source)
        self.assertIn('"item": public_request_row(row)', source)

    def test_frontend_does_not_model_or_render_private_attachment_path(self) -> None:
        for relative in (
            "apps/web/components/StaffShiftRequests.tsx",
            "apps/web/components/ScheduleChangeReview.tsx",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("attachment_path", source, relative)
            self.assertIn("has_attachment", source, relative)


if __name__ == "__main__":
    unittest.main()
