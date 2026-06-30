from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.payroll_drafts import create_payroll_draft
from api.payroll_service import PayrollDraftRequest
from core.db import fetchone, get_conn, init_db


class PayrollDraftEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "payroll.sqlite"
        conn = get_conn(self.db_path)
        try:
            init_db(conn)
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_draft(self, business_date: date) -> dict:
        payload = PayrollDraftRequest(
            period_start=date(2026, 6, 16),
            period_end=date(2026, 6, 30),
            payout_date=date(2026, 6, 30),
            run_label="Semi-monthly",
        )
        with (
            patch("api.payroll_drafts.DB_PATH", self.db_path),
            patch("api.payroll_drafts.payroll_business_date", return_value=business_date),
            patch(
                "api.payroll_drafts.must_be_payroll_user",
                return_value={"display_name": "Owner", "role_key": "owner"},
            ),
        ):
            return create_payroll_draft(payload, authorization=None, x_api_key=None)

    def test_missed_cutoff_can_be_created_after_period_end(self) -> None:
        result = self.create_draft(date(2026, 7, 1))
        self.assertTrue(result["ok"])
        self.assertEqual(result["run"]["status"], "Draft")
        self.assertEqual(result["run"]["period_start"], "2026-06-16")
        self.assertEqual(result["run"]["period_end"], "2026-06-30")

        conn = get_conn(self.db_path)
        try:
            saved = fetchone(conn, "SELECT status FROM payroll_runs")
        finally:
            conn.close()
        self.assertEqual(saved, {"status": "Draft"})

    def test_cutoff_cannot_be_created_until_period_has_ended(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.create_draft(date(2026, 6, 30))
        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
