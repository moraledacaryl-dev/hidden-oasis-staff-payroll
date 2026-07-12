from __future__ import annotations

import json
import os
import sqlite3
import unittest
from unittest.mock import patch

from core.integration_compat import ensure_legacy_integration_writer_compatibility
from core.integration_outbox import (
    claim_events,
    enqueue_employee_sync,
    enqueue_event,
    ensure_integration_schema,
    process_claimed_event,
)


class IntegrationOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_code TEXT NOT NULL,
                full_name TEXT NOT NULL,
                department TEXT,
                position TEXT,
                employment_type TEXT,
                status TEXT,
                updated_at TEXT
            )
            """
        )
        ensure_integration_schema(self.conn)
        ensure_legacy_integration_writer_compatibility(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def _enqueue(self, *, destination: str = "accounting", external_id: str = "event-1", max_attempts: int = 8) -> int:
        event_id = enqueue_event(
            self.conn,
            destination=destination,
            event_type="employee.sync",
            external_source="hidden_oasis_staff_payroll",
            external_id=external_id,
            source_type="Employee",
            source_id=1,
            payload={"external_id": external_id},
            max_attempts=max_attempts,
        )
        self.conn.commit()
        return event_id

    def test_employee_sync_queues_all_destinations_without_sensitive_fields(self) -> None:
        employee_id = self.conn.execute(
            """
            INSERT INTO employees(employee_code,full_name,department,position,employment_type,status,updated_at)
            VALUES('EMP-001','Safe Name','Admin','Clerk','Regular','Active','2026-07-13 10:00:00')
            """
        ).lastrowid
        ids = enqueue_employee_sync(self.conn, int(employee_id))
        self.conn.commit()
        rows = self.conn.execute("SELECT destination,payload_json FROM integration_outbox ORDER BY destination").fetchall()
        self.assertEqual(len(ids), 4)
        self.assertEqual({row["destination"] for row in rows}, {"accounting", "operations", "pos", "inventory"})
        for row in rows:
            payload = json.loads(row["payload_json"])
            employee = payload["payload"]["employees"][0]
            self.assertEqual(employee["employee_code"], "EMP-001")
            self.assertEqual(
                set(employee),
                {
                    "employee_code",
                    "display_name",
                    "department",
                    "position",
                    "role",
                    "active",
                    "primary_department",
                    "source_staff_id",
                },
            )
            serialized = row["payload_json"].lower()
            for forbidden in ("hourly_rate", "salary", "government", "password", "mfa", "emergency_contact"):
                self.assertNotIn(forbidden, serialized)

    def test_same_destination_and_external_id_is_idempotent(self) -> None:
        first = enqueue_event(
            self.conn,
            destination="accounting",
            event_type="employee.sync",
            external_source="hidden_oasis_staff_payroll",
            external_id="employee-sync:1:v1",
            source_type="Employee",
            source_id=1,
            payload={"value": 1},
        )
        second = enqueue_event(
            self.conn,
            destination="accounting",
            event_type="employee.sync",
            external_source="hidden_oasis_staff_payroll",
            external_id="employee-sync:1:v1",
            source_type="Employee",
            source_id=1,
            payload={"value": 2},
        )
        self.conn.commit()
        self.assertEqual(first, second)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM integration_outbox").fetchone()[0], 1)

    def test_claim_is_atomic_and_marks_processing(self) -> None:
        self._enqueue(external_id="claim-me")
        claimed = claim_events(self.conn, worker_id="test-worker")
        self.assertEqual(len(claimed), 1)
        row = self.conn.execute("SELECT status,locked_by FROM integration_outbox").fetchone()
        self.assertEqual(row["status"], "Processing")
        self.assertEqual(row["locked_by"], "test-worker")
        self.assertEqual(claim_events(self.conn, worker_id="other-worker"), [])

    def test_receiver_duplicate_response_completes_event(self) -> None:
        self._enqueue(external_id="duplicate-safe")
        row = claim_events(self.conn, worker_id="test-worker")[0]
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_ACCOUNTING_SYNC_URL": "https://accounting.example",
            "STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN": "secret",
        }), patch("core.integration_outbox._post", return_value=(200, '{"status":"already_applied"}')):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(self.conn.execute("SELECT status FROM integration_outbox").fetchone()[0], "Completed")

    def test_unconfigured_destination_retries_without_losing_event(self) -> None:
        self._enqueue(destination="inventory", external_id="not-configured")
        row = claim_events(self.conn, worker_id="test-worker")[0]
        with patch.dict(os.environ, {"STAFF_PAYROLL_INVENTORY_SYNC_URL": ""}, clear=False):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Retry")
        stored = self.conn.execute("SELECT status,attempt_count,next_attempt_at,payload_json FROM integration_outbox").fetchone()
        self.assertEqual(stored["status"], "Retry")
        self.assertEqual(stored["attempt_count"], 1)
        self.assertTrue(stored["next_attempt_at"])
        self.assertIn("not-configured", stored["payload_json"])

    def test_server_error_is_retried_with_backoff(self) -> None:
        self._enqueue(external_id="server-error")
        row = claim_events(self.conn, worker_id="test-worker")[0]
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_ACCOUNTING_SYNC_URL": "https://accounting.example",
            "STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN": "secret",
        }), patch("core.integration_outbox._post", return_value=(503, '{"detail":"temporarily unavailable"}')):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Retry")
        stored = self.conn.execute("SELECT status,attempt_count,next_attempt_at,last_error FROM integration_outbox").fetchone()
        self.assertEqual(stored["status"], "Retry")
        self.assertEqual(stored["attempt_count"], 1)
        self.assertTrue(stored["next_attempt_at"])
        self.assertIn("HTTP 503", stored["last_error"])

    def test_contract_error_goes_directly_to_dead_letter(self) -> None:
        self._enqueue(external_id="bad-contract")
        row = claim_events(self.conn, worker_id="test-worker")[0]
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_ACCOUNTING_SYNC_URL": "https://accounting.example",
            "STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN": "secret",
        }), patch("core.integration_outbox._post", return_value=(422, '{"detail":"unsupported payload"}')):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Dead Letter")
        stored = self.conn.execute("SELECT status,dead_letter_at,last_error FROM integration_outbox").fetchone()
        self.assertEqual(stored["status"], "Dead Letter")
        self.assertTrue(stored["dead_letter_at"])
        self.assertIn("HTTP 422", stored["last_error"])

    def test_retry_exhaustion_goes_to_dead_letter(self) -> None:
        self._enqueue(external_id="exhausted", max_attempts=1)
        row = claim_events(self.conn, worker_id="test-worker")[0]
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_ACCOUNTING_SYNC_URL": "https://accounting.example",
            "STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN": "secret",
        }), patch("core.integration_outbox._post", return_value=(500, "failure")):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Dead Letter")
        stored = self.conn.execute("SELECT status,attempt_count,dead_letter_at FROM integration_outbox").fetchone()
        self.assertEqual(stored["attempt_count"], 1)
        self.assertTrue(stored["dead_letter_at"])

    def test_delivery_sends_all_supported_auth_headers(self) -> None:
        self._enqueue(destination="inventory", external_id="headers")
        row = claim_events(self.conn, worker_id="test-worker")[0]
        captured: dict[str, str] = {}

        def fake_post(url: str, body: str, token: str, timeout: int):
            captured.update({"url": url, "body": body, "token": token, "timeout": str(timeout)})
            return 201, '{"status":"accepted"}'

        with patch.dict(os.environ, {
            "STAFF_PAYROLL_INVENTORY_SYNC_URL": "https://inventory.example",
            "STAFF_PAYROLL_INVENTORY_SYNC_TOKEN": "destination-secret",
        }), patch("core.integration_outbox._post", side_effect=fake_post):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(captured["token"], "destination-secret")
        self.assertEqual(captured["url"], "https://inventory.example/api/v1/integrations/staff/employees")

    def test_completed_event_remains_immutable_on_reenqueue(self) -> None:
        event_id = self._enqueue(external_id="immutable")
        self.conn.execute(
            "UPDATE integration_outbox SET status='Completed',completed_at='2026-07-13 10:00:00' WHERE id=?",
            (event_id,),
        )
        self.conn.commit()
        same_id = enqueue_event(
            self.conn,
            destination="accounting",
            event_type="employee.sync",
            external_source="hidden_oasis_staff_payroll",
            external_id="immutable",
            source_type="Employee",
            source_id=1,
            payload={"new": "payload"},
        )
        self.conn.commit()
        stored = self.conn.execute("SELECT id,status,completed_at FROM integration_outbox").fetchone()
        self.assertEqual(same_id, event_id)
        self.assertEqual(stored["status"], "Completed")
        self.assertTrue(stored["completed_at"])

    def test_legacy_ready_insert_is_normalized(self) -> None:
        self.conn.execute(
            """
            INSERT INTO integration_outbox(event_type,external_source,external_id,source_type,source_id,payload_json,status,created_at,updated_at)
            VALUES('payroll.run.paid','hidden_oasis_staff_payroll','legacy-1','Payroll Run',1,'{}','Ready','2026-07-13','2026-07-13')
            """
        )
        self.conn.commit()
        row = self.conn.execute("SELECT destination,status FROM integration_outbox WHERE external_id='legacy-1'").fetchone()
        self.assertEqual(row["destination"], "accounting")
        self.assertEqual(row["status"], "Pending")


if __name__ == "__main__":
    unittest.main()
