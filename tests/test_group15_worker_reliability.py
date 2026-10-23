from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.db import get_conn
from core import integration_outbox as outbox
from core import operations_v2_adapter as v2


class Group15WorkerReliabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "group15.sqlite"
        self.conn = get_conn(self.path)
        outbox.ensure_integration_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def enqueue(self, destination: str, external_id: str) -> int:
        event_id = outbox.enqueue_event(
            self.conn,
            destination=destination,
            event_type="employee.sync",
            external_source="group15-test",
            external_id=external_id,
            source_type="Employee",
            source_id=1,
            payload={"external_id": external_id},
        )
        self.conn.commit()
        return event_id

    def statuses(self) -> dict[str, str]:
        return {
            row["external_id"]: row["status"]
            for row in self.conn.execute(
                "SELECT external_id, status FROM integration_outbox ORDER BY id"
            )
        }

    def test_core_worker_crash_does_not_strand_unattempted_batch(self) -> None:
        for index in range(4):
            self.enqueue("inventory", f"core-{index}")
        with patch.object(outbox, "process_claimed_event", side_effect=RuntimeError("worker interrupted")) as send:
            with self.assertRaisesRegex(RuntimeError, "worker interrupted"):
                outbox.process_due_events(self.conn, limit=4, worker_id="worker-A")
        self.assertEqual(send.call_count, 1)
        self.assertEqual(self.statuses(), {
            "core-0": "Processing",
            "core-1": "Pending", "core-2": "Pending", "core-3": "Pending",
        })
        self.assertEqual(
            [r["external_id"] for r in outbox.claim_events(self.conn, limit=3, worker_id="worker-B")],
            ["core-1", "core-2", "core-3"],
        )

    def test_v2_worker_crash_does_not_strand_unattempted_batch(self) -> None:
        for index in range(4):
            self.enqueue("operations", f"v2-{index}")
        with patch.object(v2, "_process_operations_event", side_effect=RuntimeError("interrupted")) as send:
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                v2.process_due_events(self.conn, limit=4, worker_id="v2-worker")
        self.assertEqual(send.call_count, 1)
        self.assertEqual(self.statuses(), {
            "v2-0": "Processing",
            "v2-1": "Pending", "v2-2": "Pending", "v2-3": "Pending",
        })

    def test_successful_core_batch_claims_and_completes_all(self) -> None:
        for index in range(4):
            self.enqueue("inventory", f"good-{index}")
        with (
            patch.dict(os.environ, {
                "STAFF_PAYROLL_INVENTORY_SYNC_URL": "https://inventory.invalid",
                "STAFF_PAYROLL_INVENTORY_SYNC_TOKEN": "integration-test",
            }),
            patch.object(outbox, "_post", return_value=(200, '{"status":"accepted"}')) as send,
        ):
            result = outbox.process_due_events(self.conn, limit=4, worker_id="good-worker")
        self.assertEqual(result["claimed"], 4)
        self.assertEqual(result["completed"], 4)
        self.assertEqual(send.call_count, 4)
        self.assertEqual(set(self.statuses().values()), {"Completed"})

    def test_worker_limit_is_respected_and_remaining_rows_are_pending(self) -> None:
        for index in range(5):
            self.enqueue("inventory", f"batch-{index}")
        with (
            patch.dict(os.environ, {
                "STAFF_PAYROLL_INVENTORY_SYNC_URL": "https://inventory.invalid",
                "STAFF_PAYROLL_INVENTORY_SYNC_TOKEN": "integration-test",
            }),
            patch.object(outbox, "_post", return_value=(200, "{}")),
        ):
            result = v2.process_due_events(self.conn, limit=2, worker_id="limited-worker")
        self.assertEqual(result["claimed"], 2)
        self.assertEqual(result["completed"], 2)
        self.assertEqual(
            list(self.statuses().values()),
            ["Completed", "Completed", "Pending", "Pending", "Pending"],
        )

    def test_concurrent_workers_cannot_claim_the_same_event(self) -> None:
        for index in range(12):
            self.enqueue("inventory", f"concurrent-{index}")
        barrier = threading.Barrier(2, timeout=10)

        def claim(worker: str) -> list[int]:
            conn = get_conn(self.path)
            try:
                barrier.wait()
                return [
                    int(item["id"]) for item in
                    outbox.claim_events(conn, limit=6, worker_id=worker)
                ]
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(claim, "worker-A")
            b = pool.submit(claim, "worker-B")
            claimed_a = a.result(timeout=25)
            claimed_b = b.result(timeout=25)
        self.assertEqual(len(claimed_a), 6)
        self.assertEqual(len(claimed_b), 6)
        self.assertEqual(len(set(claimed_a + claimed_b)), 12)
        self.assertEqual(set(self.statuses().values()), {"Processing"})

    def test_aborted_transaction_rolls_back_source_and_outbox(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "simulate interrupted payroll"):
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute("CREATE TABLE IF NOT EXISTS group15_source (id INTEGER PRIMARY KEY, value TEXT)")
                self.conn.execute("INSERT INTO group15_source(id, value) VALUES(1, 'draft')")
                outbox.enqueue_event(
                    self.conn, destination="accounting",
                    event_type="payroll.run.approved",
                    external_source="group15-test",
                    external_id="interrupted-payment",
                    source_type="Payroll Run", source_id=1,
                    payload={"event": "not committed"},
                    schema_ready=True,
                )
                raise RuntimeError("simulate interrupted payroll")
            except BaseException:
                self.conn.rollback()
                raise
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM group15_source").fetchone()[0], 0
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM integration_outbox").fetchone()[0], 0
        )


if __name__ == "__main__":
    unittest.main()
