from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from api.cash_advance_service import ensure_schema
from api.cash_repayments import ManualRepaymentPayload, record_manual_repayment
from core.db import get_conn
from core.integration_outbox import canonical_accounting_payload


class ManualRepaymentIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "staff.sqlite"
        conn = get_conn(self.path)
        try:
            conn.execute("CREATE TABLE payroll_runs (id INTEGER PRIMARY KEY, status TEXT)")
            conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "CREATE TABLE employees (id INTEGER PRIMARY KEY, employee_code TEXT, "
                "full_name TEXT, department TEXT, position TEXT)"
            )
            conn.execute(
                "INSERT INTO employees(id, employee_code, full_name, department, position) "
                "VALUES(1, 'EMP-1', 'Example Employee', 'Operations', 'Staff')"
            )
            ensure_schema(conn)
            self.advance_id = int(conn.execute(
                """
                INSERT INTO cash_advances(
                  employee_id, advance_date, request_date, amount, repayment_method,
                  deduction_per_payroll, repayment_per_cutoff, remaining_balance,
                  outstanding_balance, ledger_opening_balance, status
                ) VALUES (1,'2026-10-20','2026-10-20',100,'Manual repayment',0,0,100,100,100,'Active')
                """
            ).lastrowid)
            conn.commit()
        finally:
            conn.close()

    def pay(self, *, key: str | None, amount: float = 30, advance_id: int | None = None,
            reference: str = "receipt-100", notes: str = "received") -> dict:
        payload = ManualRepaymentPayload(
            amount=amount, repayment_date="2026-10-20", payment_method="GCash",
            reference=reference, notes=notes, idempotency_key=key,
        )
        with (
            patch("api.cash_repayments.require_cash_advance_editor",
                  return_value={"display_name": "Owner", "role_key": "owner"}),
            patch("api.cash_repayments.get_conn", side_effect=lambda _: get_conn(self.path)),
        ):
            return record_manual_repayment(
                advance_id if advance_id is not None else self.advance_id,
                payload, authorization="Bearer token", x_api_key=None,
            )

    def rows(self) -> list[dict]:
        conn = get_conn(self.path)
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM cash_advance_repayments ORDER BY id"
            ).fetchall()]
        finally:
            conn.close()

    def test_replay_returns_same_repayment_and_does_not_deduct_twice(self) -> None:
        key = str(uuid4())
        first = self.pay(key=key)
        second = self.pay(key=key)
        self.assertFalse(first["already_recorded"])
        self.assertTrue(second["already_recorded"])
        self.assertEqual(first["repayment_id"], second["repayment_id"])
        self.assertEqual(second["summary"]["balance"], 70.0)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["idempotency_key"], key)

    def test_same_key_with_different_amount_rejected_and_not_posted(self) -> None:
        key = str(uuid4())
        self.pay(key=key)
        with self.assertRaises(HTTPException) as ctx:
            self.pay(key=key, amount=40)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(len(self.rows()), 1)

    def test_same_key_with_different_reference_rejected(self) -> None:
        key = str(uuid4())
        self.pay(key=key)
        with self.assertRaises(HTTPException) as ctx:
            self.pay(key=key, reference="a different receipt")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_reversed_request_id_cannot_repost(self) -> None:
        key = str(uuid4())
        self.pay(key=key)
        conn = get_conn(self.path)
        conn.execute("UPDATE cash_advance_repayments SET active=0")
        conn.commit()
        conn.close()
        with self.assertRaises(HTTPException) as ctx:
            self.pay(key=key)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(len(self.rows()), 1)

    def test_distinct_requests_cannot_overpay_remaining_advance(self) -> None:
        self.pay(key=str(uuid4()), amount=60)
        with self.assertRaises(HTTPException) as ctx:
            self.pay(key=str(uuid4()), amount=60)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(len(self.rows()), 1)

    def test_old_api_clients_without_request_id_still_work(self) -> None:
        result = self.pay(key=None)
        self.assertFalse(result["already_recorded"])
        self.assertIsNone(self.rows()[0]["idempotency_key"])

    def test_new_manual_repayment_queues_single_accounting_cash_receipt(self) -> None:
        key = str(uuid4())
        result = self.pay(key=key)
        conn = get_conn(self.path)
        try:
            rows = conn.execute(
                "SELECT * FROM integration_outbox WHERE event_type='cash_advance.repaid'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            row = dict(rows[0])
            self.assertEqual(row["destination"], "accounting")
            self.assertEqual(row["source_id"], result["repayment_id"])
            self.assertEqual(row["status"], "Pending")
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["external_id"], f"cash-advance-repayment:{result['repayment_id']}")
            review = canonical_accounting_payload(row["event_type"], payload)
            self.assertEqual(review["financial_effect"], "cash_in")
            self.assertEqual(review["amount"], 30.0)
            self.assertEqual(review["proposed_links"]["payment_method"], "GCash")
        finally:
            conn.close()

    def test_retries_do_not_enqueue_a_second_accounting_receipt(self) -> None:
        key = str(uuid4())
        self.pay(key=key)
        self.pay(key=key)
        conn = get_conn(self.path)
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM integration_outbox WHERE event_type='cash_advance.repaid'"
            ).fetchone()[0], 1)
        finally:
            conn.close()

    def test_failed_accounting_enqueue_rolls_back_repayment_and_balance(self) -> None:
        with patch("api.cash_repayments.enqueue_event", side_effect=RuntimeError("Outbox unavailable")):
            with self.assertRaisesRegex(RuntimeError, "Outbox unavailable"):
                self.pay(key=str(uuid4()))
        self.assertEqual(self.rows(), [])
        conn = get_conn(self.path)
        try:
            row = conn.execute(
                "SELECT remaining_balance FROM cash_advances WHERE id=?", (self.advance_id,)
            ).fetchone()
            self.assertEqual(float(row[0]), 100.0)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM integration_outbox").fetchone()[0], 0
            )
        finally:
            conn.close()

    def test_uuid_client_key_must_be_well_formed(self) -> None:
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ManualRepaymentPayload(
                amount=30, repayment_date="2026-10-20", payment_method="GCash",
                idempotency_key="not-a-valid-request-id",
            )


if __name__ == "__main__":
    unittest.main()
