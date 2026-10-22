from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api import payroll_drafts
from api.payroll_revision_service import ensure_workflow_schema
from core.db import get_conn, init_db, now_iso


class PayrollHistoryArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        handle.close()
        self.path = Path(handle.name)
        self.addCleanup(self._cleanup)
        conn = get_conn(self.path)
        init_db(conn)
        ensure_workflow_schema(conn)
        for i in range(65):
            status = ("Draft", "For Owner Review", "Approved", "Paid")[i % 4]
            period_start = "2025-01-01" if i == 0 else "2026-09-15"
            period_end = "2025-01-14" if i == 0 else "2026-09-29"
            conn.execute(
                """INSERT INTO payroll_runs(
                    period_start,period_end,payout_date,run_label,status,
                    prepared_by,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (period_start,period_end,"2026-09-30",f"Archive run {i}",status,
                 "Payroll Tester",f"2026-10-01 09:{i:02d}:00"),
            )
        for run_id in (1, 2, 3):
            conn.execute(
                "UPDATE payroll_runs SET superseded_by_run_id=? WHERE id=?",
                (65, run_id),
            )
        conn.commit()
        conn.close()
        env = patch.dict(os.environ, {"STAFF_PAYROLL_DB_PATH": str(self.path)})
        env.start()
        self.addCleanup(env.stop)

    def _cleanup(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)

    def history(self, **kwargs):
        with patch.object(payroll_drafts, "must_be_payroll_user", return_value={"role_key": "owner"}):
            return payroll_drafts.payroll_run_history(
                status=kwargs.get("status"),
                start=kwargs.get("start"),
                end=kwargs.get("end"),
                view=kwargs.get("view", "all"),
                page=kwargs.get("page", 1),
                page_size=kwargs.get("page_size", 25),
                authorization="test-token",
                x_api_key="test-key",
            )

    def test_lists_all_versions_not_just_latest_fifty(self) -> None:
        first = self.history(page=1)
        third = self.history(page=3)
        self.assertEqual(first["total"], 65)
        self.assertEqual(first["pages"], 3)
        self.assertEqual(len(first["items"]), 25)
        self.assertEqual(len(third["items"]), 15)
        self.assertEqual(len({r["id"] for r in first["items"] + self.history(page=2)["items"] + third["items"]}), 65)

    def test_historical_period_filter_runs_before_limit(self) -> None:
        old = self.history(start=date(2025, 1, 1), end=date(2025, 1, 14))
        self.assertEqual(old["total"], 1)
        self.assertEqual(old["items"][0]["id"], 1)
        self.assertEqual(old["items"][0]["run_label"], "Archive run 0")

    def test_revision_filter_distinguishes_audit_from_current(self) -> None:
        superseded = self.history(view="superseded")
        current = self.history(view="current")
        self.assertEqual(superseded["total"], 3)
        self.assertEqual(current["total"], 62)
        self.assertEqual({r["id"] for r in superseded["items"]}, {1,2,3})
        self.assertEqual(superseded["summary"]["superseded"], 3)
        self.assertEqual(superseded["summary"], current["summary"])

    def test_status_filter_before_pagination(self) -> None:
        approved = self.history(status="Approved", page_size=10)
        self.assertEqual(approved["total"], 16)
        self.assertEqual(len(approved["items"]), 10)
        self.assertTrue(all(x["status"] == "Approved" for x in approved["items"]))
        remaining = self.history(status="Approved", page=2, page_size=10)
        self.assertEqual(len(remaining["items"]), 6)

    def test_empty_page_returns_truthful_total_without_mutations(self) -> None:
        before = get_conn(self.path)
        try:
            count = before.execute("SELECT COUNT(*) FROM payroll_runs").fetchone()[0]
        finally:
            before.close()
        result = self.history(page=50, page_size=25)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 65)
        after = get_conn(self.path)
        try:
            self.assertEqual(after.execute("SELECT COUNT(*) FROM payroll_runs").fetchone()[0], count)
        finally:
            after.close()

    def test_role_denial_happens_before_database_access(self) -> None:
        with (
            patch.object(payroll_drafts, "must_be_payroll_user", side_effect=HTTPException(status_code=403, detail="Denied")),
            patch.object(payroll_drafts, "db_conn") as connection,
        ):
            with self.assertRaises(HTTPException) as caught:
                payroll_drafts.payroll_run_history(
                    status=None, start=None, end=None, view="all", page=1, page_size=25,
                    authorization="denied", x_api_key="denied",
                )
            self.assertEqual(caught.exception.status_code, 403)
            connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
