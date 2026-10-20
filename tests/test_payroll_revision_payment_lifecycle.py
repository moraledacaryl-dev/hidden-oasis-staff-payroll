from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api import payroll_mark_paid, payroll_revision_workflow
from api.payroll_mark_paid import MarkPaidRequest
from api.payroll_revision_service import ControlledRevisionPayload, ensure_workflow_schema
from core.db import fetchone, get_conn, init_db, now_iso
from core.payroll_engine import update_payroll_status


class PayrollRevisionPaymentLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        handle.close()
        self.db_path = Path(handle.name)
        conn = get_conn(self.db_path)
        init_db(conn)
        ensure_workflow_schema(conn)
        conn.close()

    def tearDown(self) -> None:
        self.db_path.unlink(missing_ok=True)
        Path(str(self.db_path) + "-wal").unlink(missing_ok=True)
        Path(str(self.db_path) + "-shm").unlink(missing_ok=True)

    def _insert_run(self, status: str, label: str, paid_at: str | None = None) -> int:
        conn = get_conn(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO payroll_runs(
                    period_start,period_end,payout_date,run_label,status,
                    prepared_by,paid_at,created_at
                ) VALUES('2026-09-15','2026-09-29','2026-09-30',?,?,?,?,?)
                """,
                (label, status, "Payroll User", paid_at, now_iso()),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _run(self, run_id: int) -> dict:
        conn = get_conn(self.db_path)
        try:
            return fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,)) or {}
        finally:
            conn.close()

    def _save_revision(self, run_id: int, treatment: str = "replace_unpaid") -> int:
        payload = ControlledRevisionPayload(
            run_label=f"Run {run_id} revision",
            revision_reason="Correct pre-payment payroll values",
            treatment=treatment,
        )
        with (
            patch.object(payroll_revision_workflow, "DB_PATH", self.db_path),
            patch.object(
                payroll_revision_workflow,
                "must_be_payroll_user",
                return_value={"role_key": "payroll", "display_name": "Payroll User"},
            ),
            patch.object(payroll_revision_workflow, "compute_payroll_with_fractional_leave", return_value=[]),
        ):
            response = payroll_revision_workflow.save_controlled_revision(
                run_id, payload, "token", "key"
            )
        return int(response["run"]["id"])

    def _approve_revision(self, run_id: int) -> None:
        conn = get_conn(self.db_path)
        try:
            with (
                patch("core.payroll_engine.build_payroll_preflight_checks", return_value=[]),
                patch("core.integration_accounting.enqueue_payroll_run"),
            ):
                update_payroll_status(conn, run_id, "For Owner Review", "Payroll User")
                update_payroll_status(conn, run_id, "Approved", "Owner")
        finally:
            conn.close()

    def _mark_paid(self, run_id: int):
        with (
            patch.object(payroll_mark_paid, "DB_PATH", self.db_path),
            patch.object(
                payroll_mark_paid,
                "must_be_payroll_user",
                return_value={"role_key": "owner", "display_name": "Owner"},
            ),
            patch.object(payroll_mark_paid, "build_payroll_preflight_checks", return_value=[]),
            patch.object(payroll_mark_paid, "apply_payroll_cash_advance_repayments") as apply_repayments,
            patch.object(payroll_mark_paid, "create_accounting_queue_for_payroll"),
            patch("core.integration_accounting.enqueue_payroll_run"),
        ):
            response = payroll_mark_paid.mark_payroll_run_paid(
                run_id,
                MarkPaidRequest(confirmation="MARK PAID"),
                "token",
                "key",
            )
        return response, apply_repayments

    def test_draft_replacement_becomes_operable_and_payable(self) -> None:
        original_id = self._insert_run("Draft", "Draft original")
        revision_id = self._save_revision(original_id)

        original = self._run(original_id)
        revision = self._run(revision_id)
        self.assertEqual(revision["revision_of_run_id"], original_id)
        self.assertEqual(revision["revision_treatment"], "replace_unpaid")
        self.assertEqual(original["superseded_by_run_id"], revision_id)
        self.assertIsNone(original["paid_at"])

        self._approve_revision(revision_id)
        response, apply_repayments = self._mark_paid(revision_id)

        self.assertTrue(response["ok"])
        self.assertEqual(self._run(revision_id)["status"], "Paid")
        self.assertEqual(self._run(original_id)["status"], "Draft")
        self.assertIsNone(self._run(original_id)["paid_at"])
        apply_repayments.assert_called_once()

    def test_approved_unpaid_replacement_can_be_reapproved_and_paid(self) -> None:
        original_id = self._insert_run("Approved", "Approved unpaid original")
        revision_id = self._save_revision(original_id)

        self._approve_revision(revision_id)
        self._mark_paid(revision_id)

        original = self._run(original_id)
        revision = self._run(revision_id)
        self.assertEqual(original["status"], "Approved")
        self.assertIsNone(original["paid_at"])
        self.assertEqual(original["superseded_by_run_id"], revision_id)
        self.assertEqual(revision["status"], "Paid")
        self.assertTrue(revision["paid_at"])

    def test_superseded_old_version_cannot_be_marked_paid(self) -> None:
        original_id = self._insert_run("Approved", "Superseded original")
        revision_id = self._save_revision(original_id)

        with self.assertRaises(HTTPException) as raised:
            self._mark_paid(original_id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("audit history only", str(raised.exception.detail))
        self.assertEqual(self._run(original_id)["superseded_by_run_id"], revision_id)
        self.assertIsNone(self._run(original_id)["paid_at"])

    def test_replacement_cannot_finalize_if_parent_became_paid(self) -> None:
        original_id = self._insert_run("Approved", "Race original")
        revision_id = self._save_revision(original_id)
        self._approve_revision(revision_id)

        conn = get_conn(self.db_path)
        try:
            conn.execute(
                "UPDATE payroll_runs SET status='Paid', paid_at=? WHERE id=?",
                (now_iso(), original_id),
            )
            conn.commit()
        finally:
            conn.close()

        with self.assertRaises(HTTPException) as raised:
            self._mark_paid(revision_id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("already paid/finalized", str(raised.exception.detail))
        self.assertEqual(self._run(revision_id)["status"], "Approved")
        self.assertIsNone(self._run(revision_id)["paid_at"])

    def test_paid_and_locked_runs_require_adjustment_revision(self) -> None:
        for status in ("Paid", "Locked"):
            with self.subTest(status=status):
                original_id = self._insert_run(
                    status,
                    f"{status} original",
                    paid_at=now_iso() if status == "Paid" else None,
                )
                with self.assertRaises(HTTPException) as raised:
                    self._save_revision(original_id, treatment="replace_unpaid")
                self.assertEqual(raised.exception.status_code, 409)
                self.assertIn("already paid", str(raised.exception.detail).lower())

    def test_paid_adjustment_keeps_original_cash_advance_repayment_active(self) -> None:
        from api.cash_advance_service import ensure_schema as ensure_cash_schema
        from core.cash_advance_payroll import apply_payroll_cash_advance_repayments

        original_id = self._insert_run("Paid", "Original paid with advance", paid_at=now_iso())
        conn = get_conn(self.db_path)
        try:
            ensure_cash_schema(conn)
            stamp = now_iso()
            employee_id = int(conn.execute(
                "INSERT INTO employees(employee_code,full_name,status,created_at,updated_at) "
                "VALUES('EMP-PAID-CA','Advance employee','Active',?,?)",
                (stamp, stamp),
            ).lastrowid)
            advance_id = int(conn.execute(
                "INSERT INTO cash_advances("
                "employee_id,request_date,advance_date,amount,outstanding_balance,"
                "remaining_balance,repayment_method,status,created_at"
                ") VALUES(?,'2026-09-15','2026-09-15',500,500,500,"
                "'Payroll deduction','Active',?)",
                (employee_id, stamp),
            ).lastrowid)
            conn.execute(
                "INSERT INTO payroll_items("
                "payroll_run_id,employee_id,gross_pay,cash_advance_deduction,"
                "total_deductions,net_pay,created_at"
                ") VALUES(?,?,1000,200,200,800,?)",
                (original_id, employee_id, stamp),
            )
            conn.commit()
            apply_payroll_cash_advance_repayments(conn, original_id, actor="Owner")
            conn.commit()
            repayment = fetchone(
                conn,
                "SELECT id,amount,active FROM cash_advance_repayments "
                "WHERE payroll_run_id=?", (original_id,),
            )
            self.assertIsNotNone(repayment)
            self.assertEqual(float(repayment["amount"]), 200.0)
            self.assertEqual(int(repayment["active"]), 1)
            original_repayment_id = int(repayment["id"])
        finally:
            conn.close()

        revision_id = self._save_revision(original_id, treatment="adjust_paid")
        conn = get_conn(self.db_path)
        try:
            # The revised item mirrors the already paid deduction; the
            # adjustment run must not settle that advance a second time.
            conn.execute(
                "INSERT INTO payroll_items("
                "payroll_run_id,employee_id,gross_pay,cash_advance_deduction,"
                "total_deductions,net_pay,created_at"
                ") VALUES(?,?,1000,200,200,800,?)",
                (revision_id, employee_id, now_iso()),
            )
            conn.commit()
        finally:
            conn.close()

        self._approve_revision(revision_id)
        with (
            patch.object(payroll_mark_paid, "DB_PATH", self.db_path),
            patch.object(payroll_mark_paid, "must_be_payroll_user", return_value={
                "role_key": "owner", "display_name": "Owner",
            }),
            patch.object(payroll_mark_paid, "build_payroll_preflight_checks", return_value=[]),
            patch.object(payroll_mark_paid, "create_accounting_queue_for_payroll"),
            patch("core.integration_accounting.enqueue_payroll_run"),
        ):
            response = payroll_mark_paid.mark_payroll_run_paid(
                revision_id, MarkPaidRequest(confirmation="MARK PAID"), "token", "key",
            )
        self.assertTrue(response["ok"])
        self.assertEqual(self._run(revision_id)["status"], "Paid")
        self.assertEqual(self._run(original_id)["status"], "Paid")
        self.assertEqual(self._run(original_id)["superseded_by_run_id"], revision_id)

        conn = get_conn(self.db_path)
        try:
            repayment = fetchone(
                conn,
                "SELECT id,amount,active,reversed_at FROM cash_advance_repayments "
                "WHERE payroll_run_id=?", (original_id,),
            )
            self.assertEqual(int(repayment["id"]), original_repayment_id)
            self.assertEqual(float(repayment["amount"]), 200.0)
            self.assertEqual(int(repayment["active"]), 1)
            self.assertIsNone(repayment["reversed_at"])
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM cash_advance_repayments "
                    "WHERE payroll_run_id=?", (revision_id,),
                ).fetchone()[0], 0,
            )
            from api.cash_advance_service import recalculate_balance
            summary = recalculate_balance(conn, advance_id)
            self.assertEqual(summary["balance"], 300.0)
            audit = fetchone(
                conn,
                "SELECT details FROM audit_logs WHERE table_name='payroll_runs' "
                "AND record_id=? AND action='Paid payroll superseded by revision' "
                "ORDER BY id DESC LIMIT 1", (original_id,),
            )
            self.assertIn("repayments preserved", audit["details"])
        finally:
            conn.close()

    def test_direct_core_paid_transition_is_not_allowed_for_revision(self) -> None:
        original_id = self._insert_run("Approved", "Core guard original")
        revision_id = self._save_revision(original_id)
        self._approve_revision(revision_id)

        conn = get_conn(self.db_path)
        try:
            with self.assertRaisesRegex(ValueError, "controlled revision payment workflow"):
                update_payroll_status(conn, revision_id, "Paid", "Owner")
        finally:
            conn.close()


class PayrollRevisionFrontendGuardTests(unittest.TestCase):
    def test_superseded_versions_do_not_offer_final_lifecycle_actions(self) -> None:
        controls = Path("apps/web/components/PayrollLifecycleButtons.tsx").read_text(encoding="utf-8")
        cutoff = Path("apps/web/app/cutoff/page.tsx").read_text(encoding="utf-8")
        review = Path("apps/web/app/payroll/runs/[id]/page.tsx").read_text(encoding="utf-8")

        self.assertIn("supersededByRunId?: number | null", controls)
        self.assertIn('!supersededByRunId && role === "owner" && status === "Approved"', controls)
        self.assertIn("Superseded by run #", controls)
        self.assertIn("supersededByRunId={run.superseded_by_run_id}", cutoff)
        self.assertIn("!run.superseded_by_run_id ? <MarkPaidButton", review)

    def test_legacy_paid_endpoint_delegates_to_canonical_payment_workflow(self) -> None:
        source = Path("api/payroll_drafts.py").read_text(encoding="utf-8")
        self.assertIn("canonical_mark_paid(", source)
        self.assertIn('MarkPaidRequest(confirmation="MARK PAID")', source)


if __name__ == "__main__":
    unittest.main()
