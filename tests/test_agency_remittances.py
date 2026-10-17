from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.statutory_agency_remittances import (
    RemittanceRequest, add_remittance, ensure_schema, list_remittances,
)
from core.db import get_conn


class AgencyRemittanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite"
        with get_conn(self.path) as conn:
            ensure_schema(conn)
            conn.commit()
        self.patch = patch("api.security.configured_db_path", return_value=self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_duplicate_receipt_rejected_and_first_payment_preserved(self):
        user = {"display_name": "Payroll Owner"}
        first = RemittanceRequest(program="sss", contribution_month="2026-10",
            payment_date=date(2026, 10, 17), amount=Decimal("1234.50"),
            reference="OR-001")
        result = add_remittance(first, user=user)
        self.assertTrue(result["ok"])
        with self.assertRaises(HTTPException) as raised:
            add_remittance(first.model_copy(update={"reference": " or-001 "}), user=user)
        self.assertEqual(raised.exception.status_code, 409)
        items = list_remittances("2026-10", user=user)["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["amount"], 1234.50)

    def test_same_receipt_different_agency_is_allowed(self):
        user = {"display_name": "Payroll Owner"}
        for program in ("sss", "philhealth"):
            result = add_remittance(RemittanceRequest(program=program,
                contribution_month="2026-10", payment_date=date(2026, 10, 17),
                amount=Decimal("100.00"), reference="OR-002"), user=user)
            self.assertTrue(result["ok"])
        self.assertEqual(len(list_remittances("2026-10", user=user)["items"]), 2)


if __name__ == "__main__":
    unittest.main()
