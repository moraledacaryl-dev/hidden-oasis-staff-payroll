from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from core.db import get_conn
from core.integration_outbox import enqueue_event, ensure_integration_schema
from core.observability import utc_now
from scripts.audit_stale_outbox_claims import inspect_claims, main


class Group15StalledClaimAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "outbox # audit.sqlite"
        conn = get_conn(self.path)
        try:
            ensure_integration_schema(conn)
        finally:
            conn.close()

    def add_processing(self, external_id: str, *, lock: str | None, destination: str = "accounting") -> None:
        conn = get_conn(self.path)
        try:
            item_id = enqueue_event(
                conn, destination=destination, event_type="employee.sync",
                external_source="group15-stale-audit", external_id=external_id,
                source_type="Employee", source_id=1, payload={"marker": external_id},
            )
            conn.execute(
                "UPDATE integration_outbox SET status='Processing', locked_at=?, locked_by=? WHERE id=?",
                (lock, "test-worker", item_id),
            )
            conn.commit()
        finally:
            conn.close()

    def test_empty_and_recent_claims_do_not_trigger_replay(self) -> None:
        baseline = inspect_claims(self.path)
        self.assertEqual(baseline["processing_total"], 0)
        self.assertEqual(baseline["stale_or_unknown_total"], 0)
        stamp = utc_now().isoformat()
        self.add_processing("fresh", lock=stamp)
        result = inspect_claims(self.path)
        self.assertEqual(result["processing_total"], 1)
        self.assertEqual(result["stale_or_unknown_total"], 0)
        self.assertFalse(result["automatic_replay_authorized"])

    def test_stale_and_missing_lock_timestamp_require_manual_review(self) -> None:
        old = (utc_now() - timedelta(hours=2)).isoformat()
        self.add_processing("stale", lock=old, destination="operations")
        self.add_processing("unknown", lock=None)
        result = inspect_claims(self.path, stale_minutes=15)
        self.assertEqual(result["status"], "manual_review_required")
        self.assertEqual(result["processing_total"], 2)
        self.assertEqual(result["stale_or_unknown_total"], 2)
        self.assertEqual(result["invalid_lock_timestamp_total"], 1)
        self.assertEqual(result["destinations"]["operations"]["stale_or_unknown"], 1)
        self.assertFalse(result["accounting_posting_authorized"])
        self.assertNotIn("external_id", json.dumps(result))
        self.assertNotIn("source_id", json.dumps(result))
        self.assertNotIn("payload", json.dumps(result))

    def test_audit_is_read_only_and_does_not_modify_sqlite(self) -> None:
        old = (utc_now() - timedelta(hours=3)).isoformat()
        self.add_processing("stale", lock=old)
        conn = sqlite3.connect(self.path)
        try:
            before = conn.execute(
                "SELECT id,status,locked_at,attempt_count,payload_json FROM integration_outbox"
            ).fetchall()
        finally:
            conn.close()
        result = inspect_claims(self.path)
        self.assertEqual(result["stale_or_unknown_total"], 1)
        conn = sqlite3.connect(self.path)
        try:
            after = conn.execute(
                "SELECT id,status,locked_at,attempt_count,payload_json FROM integration_outbox"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(before, after)

    def test_missing_database_is_not_created_and_fails_closed(self) -> None:
        missing = Path(self.temp.name) / "no-such-database.sqlite"
        with self.assertRaisesRegex(ValueError, "existing absolute database"):
            inspect_claims(missing)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
