from __future__ import annotations

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
            self.assertIn("EMP-001", row["payload_json"])
            self.assertNotIn("hourly_rate", row["payload_json"])
            self.assertNotIn("government", row["payload_json"])

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
        enqueue_event(
            self.conn,
            destination="accounting",
            event_type="employee.sync",
            external_source="hidden_oasis_staff_payroll",
            external_id="claim-me",
            source_type="Employee",
            source_id=1,
            payload={},
        )
        self.conn.commit()
        claimed = claim_events(self.conn, worker_id="test-worker")
        self.assertEqual(len(claimed), 1)
        row = self.conn.execute("SELECT status,locked_by FROM integration_outbox").fetchone()
        self.assertEqual(row["status"], "Processing")
        self.assertEqual(row["locked_by"], "test-worker")

    def test_receiver_duplicate_response_completes_event(self) -> None:
        enqueue_event(
            self.conn,
            destination="accounting",
            event_type="employee.sync",
            external_source="hidden_oasis_staff_payroll",
            external_id="duplicate-safe",
            source_type="Employee",
            source_id=1,
            payload={},
        )
        self.conn.commit()
        row = claim_events(self.conn, worker_id="test-worker")[0]
        with patch.dict(os.environ, {
            "STAFF_PAYROLL_ACCOUNTING_SYNC_URL": "https://accounting.example",
            "STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN": "secret",
        }), patch("core.integration_outbox._post", return_value=(200, '{"status":"already_applied"}')):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(self.conn.execute("SELECT status FROM integration_outbox").fetchone()[0], "Completed")

    def test_unconfigured_destination_retries_without_losing_event(self) -> None:
        enqueue_event(
            self.conn,
            destination="inventory",
            event_type="employee.sync",
            external_source="hidden_oasis_staff_payroll",
            external_id="not-configured",
            source_type="Employee",
            source_id=1,
            payload={},
        )
        self.conn.commit()
        row = claim_events(self.conn, worker_id="test-worker")[0]
        with patch.dict(os.environ, {"STAFF_PAYROLL_INVENTORY_SYNC_URL": ""}, clear=False):
            result = process_claimed_event(self.conn, row)
        self.assertEqual(result["status"], "Retry")
        stored = self.conn.execute("SELECT status,attempt_count,next_attempt_at FROM integration_outbox").fetchone()
        self.assertEqual(stored["status"], "Retry")
        self.assertEqual(stored["attempt_count"], 1)
        self.assertTrue(stored["next_attempt_at"])

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
