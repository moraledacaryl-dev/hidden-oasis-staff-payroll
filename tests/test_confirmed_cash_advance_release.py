from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.cash_advance_service import CashAdvancePayload, ensure_schema
from api.cash_advances import (
    ReleasePayload,
    approve_cash_advance,
    cancel_cash_advance,
    confirm_cash_advance_release,
    save_cash_advance,
    LifecyclePayload,
)
from api.cash_repayments import ManualRepaymentPayload, record_manual_repayment
from core.db import get_conn
from core.integration_outbox import canonical_accounting_payload


class ConfirmedCashAdvanceReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "staff.sqlite"
        with get_conn(self.path) as conn:
            conn.executescript("""
                CREATE TABLE payroll_runs (id INTEGER PRIMARY KEY, status TEXT, period_start TEXT, period_end TEXT);
                CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE employees (
                    id INTEGER PRIMARY KEY, employee_code TEXT, full_name TEXT,
                    department TEXT, position TEXT
                );
                CREATE TABLE audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT, action TEXT, table_name TEXT, record_id INTEGER,
                    details TEXT, created_at TEXT
                );
                CREATE TABLE cash_drawer_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    movement_date TEXT, drawer_name TEXT, movement_type TEXT,
                    source_type TEXT, source_id INTEGER, amount REAL, method TEXT,
                    reference TEXT, description TEXT, created_by TEXT,
                    status TEXT, created_at TEXT
                );
                INSERT INTO employees VALUES (1,'EMP-TEST','Fixture Employee','Front Desk','Staff');
            """)
            ensure_schema(conn)
            conn.commit()
        self.user = {"id": 1, "display_name": "Owner", "role_key": "owner"}

    def connection(self, _):
        return get_conn(self.path)

    def advance(self):
        with (
            patch("api.cash_advances.require_cash_advance_creator", return_value=self.user),
            patch("api.cash_advances.get_conn", side_effect=self.connection),
        ):
            row = save_cash_advance(
                CashAdvancePayload(
                    employee_id=1, advance_date="2026-10-20", amount=3000,
                    repayment_method="Payroll deduction", deduction_per_payroll=500,
                ),
                authorization="Bearer test", x_api_key=None,
            )
        advance_id = int(row["item"]["id"])
        with (
            patch("api.cash_advances.require_cash_advance_editor", return_value=self.user),
            patch("api.cash_advances.get_conn", side_effect=self.connection),
        ):
            approve_cash_advance(advance_id, authorization="Bearer test", x_api_key=None)
        return advance_id

    def confirm(self, advance_id, *, method="GCash", reference="GC-TEST-123",
                confirmed=True, date="2026-10-20"):
        with (
            patch("api.cash_advances.require_cash_advance_editor", return_value=self.user),
            patch("api.cash_advances.get_conn", side_effect=self.connection),
        ):
            return confirm_cash_advance_release(
                advance_id,
                ReleasePayload(
                    release_date=date, release_method=method,
                    reference=reference, confirmed_received=confirmed,
                ),
                authorization="Bearer test", x_api_key=None,
            )

    def read(self, query, params=()):
        conn = get_conn(self.path)
        try:
            return [dict(r) for r in conn.execute(query, params)]
        finally:
            conn.close()

    def test_approval_does_not_create_release_outbox(self):
        advance_id = self.advance()
        rows = self.read("SELECT * FROM integration_outbox") if self.read(
            "SELECT name FROM sqlite_master WHERE name='integration_outbox'"
        ) else []
        self.assertEqual(rows, [])
        self.assertEqual(self.read(
            "SELECT release_confirmation_required, released_at FROM cash_advances WHERE id=?",
            (advance_id,),
        )[0], {"release_confirmation_required": 1, "released_at": None})

    def test_explicit_gcash_release_queues_one_reviewable_event(self):
        advance_id = self.advance()
        first = self.confirm(advance_id)
        second = self.confirm(advance_id)
        self.assertFalse(first["already_recorded"])
        self.assertTrue(second["already_recorded"])
        records = self.read("SELECT * FROM integration_outbox")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_type"], "cash_advance.released")
        self.assertEqual(records[0]["destination"], "accounting")
        self.assertEqual(records[0]["status"], "Pending")
        import json
        envelope = json.loads(records[0]["payload_json"])
        effect = canonical_accounting_payload("cash_advance.released", envelope)
        self.assertEqual(effect["financial_effect"], "cash_out")
        self.assertEqual(effect["amount"], 3000)
        advance = self.read("SELECT released_at, release_method, release_reference FROM cash_advances")[0]
        self.assertEqual(advance["release_method"], "GCash")
        self.assertEqual(advance["release_reference"], "GC-TEST-123")
        self.assertEqual(advance["released_at"], "2026-10-20")
        self.assertEqual(self.read("SELECT * FROM cash_drawer_movements"), [])

    def test_changed_reference_after_release_is_rejected(self):
        advance_id = self.advance()
        self.confirm(advance_id)
        with self.assertRaises(HTTPException) as error:
            self.confirm(advance_id, reference="GC-OTHER-REFERENCE")
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.read("SELECT * FROM integration_outbox")), 1)

    def test_cash_drawer_movement_and_outbox_are_atomic_and_unique(self):
        advance_id = self.advance()
        self.confirm(advance_id, method="Cash Drawer", reference="VOUCHER-44")
        self.confirm(advance_id, method="Cash Drawer", reference="VOUCHER-44")
        movements = self.read("SELECT * FROM cash_drawer_movements")
        self.assertEqual(len(movements), 1)
        self.assertEqual(movements[0]["amount"], 3000)
        self.assertEqual(movements[0]["reference"], "VOUCHER-44")
        self.assertEqual(len(self.read("SELECT * FROM integration_outbox")), 1)

    def test_outbox_failure_rolls_back_release_and_drawer_movement(self):
        advance_id = self.advance()
        with patch("api.cash_advances.enqueue_event", side_effect=RuntimeError("injected delivery failure")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.confirm(advance_id, method="Cash Drawer", reference="VOUCHER-44")
        self.assertEqual(self.read("SELECT * FROM cash_drawer_movements"), [])
        self.assertIsNone(self.read("SELECT released_at FROM cash_advances")[0]["released_at"])
        self.assertEqual(self.read("SELECT * FROM cash_advance_lifecycle_events WHERE to_status='Released'"), [])

    def test_unconfirmed_and_futuristic_release_is_rejected(self):
        advance_id = self.advance()
        with self.assertRaises(HTTPException) as error:
            self.confirm(advance_id, confirmed=False)
        self.assertEqual(error.exception.status_code, 422)
        with self.assertRaises(HTTPException) as error:
            self.confirm(advance_id, date="2099-01-01")
        self.assertEqual(error.exception.status_code, 422)

    def test_legacy_advance_cannot_be_replayed_as_new_release(self):
        advance_id = self.advance()
        conn = get_conn(self.path)
        conn.execute("UPDATE cash_advances SET release_confirmation_required=0 WHERE id=?", (advance_id,))
        conn.commit()
        conn.close()
        with self.assertRaises(HTTPException) as error:
            self.confirm(advance_id)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.read("SELECT * FROM integration_outbox"), [])

    def test_repayment_cannot_be_recorded_before_release(self):
        advance_id = self.advance()
        with (
            patch("api.cash_repayments.require_cash_advance_editor", return_value=self.user),
            patch("api.cash_repayments.get_conn", side_effect=self.connection),
        ):
            with self.assertRaises(HTTPException) as error:
                record_manual_repayment(
                    advance_id,
                    ManualRepaymentPayload(
                        amount=200, repayment_date="2026-10-21", payment_method="GCash",
                        reference="repayment-200",
                    ),
                    authorization="Bearer test", x_api_key=None,
                )
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.read("SELECT * FROM cash_advance_repayments"), [])

    def test_released_advance_cannot_be_cancelled_as_undisbursed(self):
        advance_id = self.advance()
        self.confirm(advance_id)
        with (
            patch("api.cash_advances.require_cash_advance_editor", return_value=self.user),
            patch("api.cash_advances.get_conn", side_effect=self.connection),
        ):
            with self.assertRaises(HTTPException) as error:
                cancel_cash_advance(
                    advance_id, LifecyclePayload(reason="Mistaken record"),
                    authorization="Bearer test", x_api_key=None,
                )
        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
