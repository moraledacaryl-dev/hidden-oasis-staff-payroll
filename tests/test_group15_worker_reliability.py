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
        self.conn.execute("CREATE TABLE group15_source (id INTEGER PRIMARY KEY, value TEXT)")
        self.conn.commit()
        with self.assertRaisesRegex(RuntimeError, "simulate interrupted payroll"):
            self.conn.execute("BEGIN IMMEDIATE")
            try:
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


class Group15ConcurrentRepaymentTests(unittest.TestCase):
    """Real SQLite concurrent payment posts; no HTTP calls or production DB."""

    def setUp(self) -> None:
        from api.cash_advance_service import ensure_schema
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "concurrent_repayments.sqlite"
        conn = get_conn(self.path)
        try:
            conn.execute("CREATE TABLE payroll_runs (id INTEGER PRIMARY KEY, status TEXT)")
            conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "CREATE TABLE employees (id INTEGER PRIMARY KEY, employee_code TEXT, "
                "full_name TEXT, department TEXT, position TEXT)"
            )
            conn.execute(
                "INSERT INTO employees(id,employee_code,full_name,department,position) "
                "VALUES(1,'G15','Concurrent Employee','Ops','Staff')"
            )
            ensure_schema(conn)
            self.advance_id = int(conn.execute(
                """INSERT INTO cash_advances(
                    employee_id,advance_date,request_date,amount,repayment_method,
                    deduction_per_payroll,repayment_per_cutoff,remaining_balance,
                    outstanding_balance,ledger_opening_balance,status
                ) VALUES(1,'2026-10-23','2026-10-23',100,'Manual repayment',0,0,100,100,100,'Active')"""
            ).lastrowid)
            conn.commit()
        finally:
            conn.close()

    def _concurrent_payments(self, *, same_key: bool, amount: float):
        from uuid import uuid4
        from api.cash_repayments import ManualRepaymentPayload, record_manual_repayment
        from fastapi import HTTPException

        shared = str(uuid4())
        keys = [shared, shared if same_key else str(uuid4())]
        barrier = threading.Barrier(2, timeout=10)

        def request(key: str):
            payload = ManualRepaymentPayload(
                amount=amount, repayment_date="2026-10-23",
                payment_method="GCash", reference="concurrent-receipt",
                notes="concurrency test", idempotency_key=key,
            )
            barrier.wait()
            try:
                return record_manual_repayment(
                    self.advance_id, payload, authorization="Bearer test", x_api_key=None,
                )
            except HTTPException as exc:
                return {"error_status": exc.status_code}

        with (
            patch(
                "api.cash_repayments.require_cash_advance_editor",
                return_value={"display_name": "Owner", "role_key": "owner"},
            ),
            patch(
                "api.cash_repayments.get_conn",
                side_effect=lambda _: get_conn(self.path),
            ),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(request, key) for key in keys]
                return [future.result(timeout=35) for future in futures]

    def _counts(self) -> tuple[int, int, float]:
        conn = get_conn(self.path)
        try:
            repayments = conn.execute(
                "SELECT COUNT(*) FROM cash_advance_repayments"
            ).fetchone()[0]
            outbox = conn.execute(
                "SELECT COUNT(*) FROM integration_outbox "
                "WHERE event_type='cash_advance.repaid'"
            ).fetchone()[0]
            balance = conn.execute(
                "SELECT remaining_balance FROM cash_advances WHERE id=?",
                (self.advance_id,),
            ).fetchone()[0]
            return int(repayments), int(outbox), float(balance)
        finally:
            conn.close()

    def test_same_key_concurrent_requests_apply_once(self) -> None:
        results = self._concurrent_payments(same_key=True, amount=30)
        self.assertEqual(len([r for r in results if r.get("already_recorded") is False]), 1)
        self.assertEqual(len([r for r in results if r.get("already_recorded") is True]), 1)
        self.assertEqual(len({r["repayment_id"] for r in results}), 1)
        self.assertEqual(self._counts(), (1, 1, 70.0))

    def test_distinct_concurrent_requests_cannot_overpay(self) -> None:
        results = self._concurrent_payments(same_key=False, amount=60)
        self.assertEqual(len([r for r in results if r.get("already_recorded") is False]), 1)
        self.assertEqual(len([r for r in results if r.get("error_status") == 422]), 1)
        self.assertEqual(self._counts(), (1, 1, 40.0))


if __name__ == "__main__":
    unittest.main()
