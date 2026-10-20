from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api import integrations
from core.db import get_conn
from core.integration_outbox import enqueue_event, ensure_integration_schema


class IntegrationOwnerRetrySafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "integration.sqlite"
        with get_conn(self.db_path) as conn:
            ensure_integration_schema(conn)
            self.event_id = enqueue_event(
                conn,
                destination="accounting",
                event_type="payroll.run.paid",
                external_source="hidden_oasis_staff_payroll",
                external_id="retry-safety-test",
                source_type="Payroll Run",
                source_id=10,
                payload={"event_type": "payroll.run.paid"},
            )
            conn.commit()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _set_status(self, status: str) -> None:
        with get_conn(self.db_path) as conn:
            conn.execute(
                "UPDATE integration_outbox SET status=?,locked_by='worker-1',"
                "locked_at='2026-10-20 12:00:00',last_error='previous error' WHERE id=?",
                (status, self.event_id),
            )
            conn.commit()

    def _retry(self):
        with patch.object(integrations, "configured_db_path", return_value=self.db_path):
            return integrations.retry_event(self.event_id, user={"role_key": "owner"})

    def _row(self):
        with get_conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT status,locked_by,last_error FROM integration_outbox WHERE id=?",
                (self.event_id,),
            ).fetchone()
            return tuple(row)

    def test_owner_cannot_unlock_an_inflight_worker(self) -> None:
        self._set_status("Processing")
        with self.assertRaises(HTTPException) as raised:
            self._retry()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self._row(), ("Processing", "worker-1", "previous error"))

    def test_owner_cannot_retry_completed_delivery(self) -> None:
        self._set_status("Completed")
        with self.assertRaises(HTTPException) as raised:
            self._retry()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self._row(), ("Completed", "worker-1", "previous error"))

    def test_owner_can_explicitly_retry_dead_letter(self) -> None:
        self._set_status("Dead Letter")
        response = self._retry()
        self.assertEqual(response["status"], "Retry")
        self.assertEqual(self._row(), ("Retry", None, None))

    def test_retry_uses_atomic_status_guard_when_row_changed_since_lookup(self) -> None:
        self._set_status("Processing")
        with patch.object(integrations, "configured_db_path", return_value=self.db_path), (
            patch.object(
                integrations, "fetchone",
                return_value={"id": self.event_id, "status": "Retry"},
            )
        ):
            with self.assertRaises(HTTPException) as raised:
                integrations.retry_event(self.event_id, user={"role_key": "owner"})
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self._row(), ("Processing", "worker-1", "previous error"))


    def _set_lock_age(self, minutes: int) -> None:
        locked_at = (
            datetime.now(timezone.utc) - timedelta(minutes=minutes)
        ).strftime("%Y-%m-%d %H:%M:%S")
        with get_conn(self.db_path) as conn:
            conn.execute(
                "UPDATE integration_outbox SET status='Processing',locked_by='worker-1',"
                "locked_at=?,last_error='Original worker timeout' WHERE id=?",
                (locked_at, self.event_id),
            )
            conn.commit()

    def _recover(self, confirmation: str = "RECOVER STALE EVENT", reason: str = "Worker service crashed during delivery"):
        with patch.object(integrations, "configured_db_path", return_value=self.db_path):
            return integrations.recover_stale_event(
                self.event_id,
                integrations.StaleEventRecoveryRequest(
                    confirmation=confirmation, reason=reason,
                ),
                user={"role_key": "owner", "display_name": "Payroll Owner"},
            )

    def test_owner_may_recover_abandoned_claim_older_than_15_minutes(self) -> None:
        self._set_lock_age(20)
        response = self._recover()
        self.assertEqual(response["status"], "Retry")
        with get_conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT status,locked_by,locked_at,last_error,next_attempt_at,"
                "attempt_count,payload_json FROM integration_outbox WHERE id=?",
                (self.event_id,),
            ).fetchone()
            self.assertEqual(row["status"], "Retry")
            self.assertIsNone(row["locked_by"])
            self.assertIsNone(row["locked_at"])
            self.assertIn("Payroll Owner", row["last_error"])
            self.assertIn("Worker service crashed", row["last_error"])
            self.assertIn("Original worker timeout", row["last_error"])
            self.assertTrue(row["next_attempt_at"])
            self.assertEqual(row["attempt_count"], 0)
            self.assertIn("payroll.run.paid", row["payload_json"])

    def test_recent_processing_claim_cannot_be_recovered(self) -> None:
        self._set_lock_age(1)
        with self.assertRaises(HTTPException) as raised:
            self._recover()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self._row(), ("Processing", "worker-1", "Original worker timeout"))

    def test_nonprocessing_event_cannot_be_recovered(self) -> None:
        self._set_status("Completed")
        with self.assertRaises(HTTPException) as raised:
            self._recover()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self._row(), ("Completed", "worker-1", "previous error"))

    def test_stale_recovery_requires_exact_owner_confirmation(self) -> None:
        self._set_lock_age(20)
        with self.assertRaises(HTTPException) as raised:
            self._recover(confirmation="RECOVER")
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self._row(), ("Processing", "worker-1", "Original worker timeout"))

    def test_atomic_guard_rejects_claim_that_changed_before_update(self) -> None:
        self._set_lock_age(1)
        with patch.object(integrations, "configured_db_path", return_value=self.db_path), patch.object(
            integrations, "fetchone", return_value={"id": self.event_id},
        ):
            with self.assertRaises(HTTPException) as raised:
                integrations.recover_stale_event(
                    self.event_id,
                    integrations.StaleEventRecoveryRequest(
                        confirmation="RECOVER STALE EVENT",
                        reason="Worker service was terminated unexpectedly",
                    ),
                    user={"role_key": "owner", "display_name": "Payroll Owner"},
                )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self._row(), ("Processing", "worker-1", "Original worker timeout"))


if __name__ == "__main__":
    unittest.main()
