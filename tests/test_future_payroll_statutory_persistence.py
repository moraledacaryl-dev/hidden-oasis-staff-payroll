from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from api.payroll_drafts import create_payroll_draft
from api.payroll_recalculate import recalculate_draft
from api.payroll_service import PayrollDraftRequest, create_payroll_draft as create_legacy_draft
from core.db import get_conn, init_db
from core.payroll_engine import PayrollResult
from core.statutory_snapshots import persist_computed_draft_snapshots


class FuturePayrollStatutoryPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "staff.sqlite"
        with get_conn(self.db) as conn:
            init_db(conn)
            self.employee_id = int(conn.execute(
                """INSERT INTO employees(employee_code,full_name,status,created_at,updated_at)
                VALUES('SP-TEST','Statutory Test Employee','Active','2026-01-01','2026-01-01')"""
            ).lastrowid)
            conn.commit()

    def calculation(self, *, gross: float = 2000, sss: float = 100, by_month=None) -> PayrollResult:
        result = PayrollResult(
            employee_id=self.employee_id,
            employee_code="SP-TEST",
            full_name="Statutory Test Employee",
            regular_pay=gross,
            gross_pay=gross,
            sss_ee=sss,
            total_deductions=sss,
            net_pay=gross - sss,
            warnings=[],
        )
        result._statutory_snapshots = by_month if by_month is not None else {
            date(2026, 6, 1): {
                "gross_pay": gross, "sss_ee": sss,
            }
        }
        return result

    def draft(self, result: PayrollResult, *, start=date(2026, 6, 15),
              end=date(2026, 6, 29), label="Semi-monthly") -> int:
        payload = PayrollDraftRequest(
            period_start=start,
            period_end=end,
            payout_date=end,
            run_label=label,
        )
        with (
            patch("api.payroll_drafts.DB_PATH", self.db),
            patch("api.payroll_drafts.payroll_business_date", return_value=date(2026, 8, 1)),
            patch("api.payroll_drafts.must_be_payroll_user", return_value={
                "display_name": "Payroll Owner", "role_key": "owner",
            }),
            patch("api.payroll_drafts.build_payroll_preflight_checks", return_value=[]),
            patch("api.payroll_drafts.compute_payroll_per_shift", return_value=[result]),
            patch("api.payroll_drafts.apply_fractional_paid_leave_adjustment", side_effect=lambda conn, result, s, e: result),
            patch("api.payroll_drafts._apply_period_cash_advance_deduction", side_effect=lambda conn, result, s, e: result),
        ):
            response = create_payroll_draft(payload, authorization=None, x_api_key=None)
        return int(response["run"]["id"])

    def recalc(self, run_id: int, results: list[PayrollResult]) -> None:
        with (
            patch("api.payroll_recalculate.DB_PATH", self.db),
            patch("api.payroll_recalculate.must_be_payroll_user", return_value={
                "display_name": "Payroll Owner", "role_key": "owner",
            }),
            patch("api.payroll_recalculate.build_payroll_preflight_checks", return_value=[]),
            patch("api.payroll_recalculate._adjustments", return_value={}),
            patch("api.payroll_recalculate.compute_payroll_per_shift", return_value=results),
            patch("api.payroll_recalculate.apply_fractional_paid_leave_adjustments", side_effect=lambda conn, results, s, e: results),
        ):
            recalculate_draft(run_id, authorization=None, x_api_key=None)

    def snapshots(self, run_id: int) -> list[tuple]:
        with get_conn(self.db) as conn:
            return [
                tuple(row)
                for row in conn.execute(
                    """SELECT month_start, gross_pay, sss_ee FROM payroll_statutory_months
                    WHERE payroll_run_id=? ORDER BY month_start""",
                    (run_id,),
                )
            ]

    def test_current_draft_saves_snapshot_with_payroll_item(self) -> None:
        run_id = self.draft(self.calculation())
        self.assertEqual(self.snapshots(run_id), [("2026-06-01", 2000.0, 100.0)])
        with get_conn(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM payroll_items WHERE payroll_run_id=?", (run_id,)
            ).fetchone()[0], 1)

    def test_legacy_draft_api_saves_monthly_snapshot_as_well(self) -> None:
        result = self.calculation()
        payload = PayrollDraftRequest(
            period_start=date(2026, 6, 15),
            period_end=date(2026, 6, 29),
            payout_date=date(2026, 6, 30),
            run_label="Legacy draft",
        )
        with (
            patch("api.payroll_service.DB_PATH", self.db),
            patch("api.payroll_service.must_be_payroll_user", return_value={
                "display_name": "Payroll Owner", "role_key": "owner",
            }),
            patch("api.payroll_service.build_payroll_preflight_checks", return_value=[]),
            patch("api.payroll_service.compute_payroll", return_value=[result]),
        ):
            response = create_legacy_draft(payload, authorization=None, x_api_key=None)
        self.assertEqual(self.snapshots(int(response["run"]["id"])), [
            ("2026-06-01", 2000.0, 100.0)
        ])

    def test_cross_month_cutoff_preserves_dated_month_gross_without_guessing(self) -> None:
        result = self.calculation(by_month={
            date(2026, 6, 1): {"gross_pay": 100},
            date(2026, 7, 1): {"gross_pay": 1900, "sss_ee": 100},
        })
        run_id = self.draft(
            result, start=date(2026, 6, 30), end=date(2026, 7, 14),
            label="Manual cross-month",
        )
        self.assertEqual(self.snapshots(run_id), [
            ("2026-06-01", 100.0, 0.0),
            ("2026-07-01", 1900.0, 100.0),
        ])

    def test_missing_dated_snapshot_fails_closed_and_rolls_back_draft(self) -> None:
        result = self.calculation()
        del result._statutory_snapshots
        with self.assertRaises(ValueError):
            self.draft(result)
        with get_conn(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payroll_runs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payroll_items").fetchone()[0], 0)

    def test_recalculate_replaces_only_draft_snapshot_rows(self) -> None:
        run_id = self.draft(self.calculation())
        self.recalc(run_id, [self.calculation(gross=3000, sss=125)])
        self.assertEqual(self.snapshots(run_id), [("2026-06-01", 3000.0, 125.0)])
        with get_conn(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM payroll_statutory_months WHERE payroll_run_id=?",
                (run_id,),
            ).fetchone()[0], 1)

    def test_recalculate_removes_snapshots_for_removed_draft_employee(self) -> None:
        run_id = self.draft(self.calculation())
        self.recalc(run_id, [])
        self.assertEqual(self.snapshots(run_id), [])
        with get_conn(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM payroll_items WHERE payroll_run_id=?",
                (run_id,),
            ).fetchone()[0], 0)

    def test_missing_earlier_paid_month_snapshot_blocks_later_draft_without_mutation(self) -> None:
        earlier_id = self.draft(
            self.calculation(), start=date(2026, 6, 1), end=date(2026, 6, 14)
        )
        with get_conn(self.db) as conn:
            conn.execute("UPDATE payroll_runs SET status='Paid' WHERE id=?", (earlier_id,))
            conn.execute("DELETE FROM payroll_statutory_months WHERE payroll_run_id=?", (earlier_id,))
            conn.commit()

        with self.assertRaisesRegex(ValueError, "lacks a statutory snapshot"):
            self.draft(self.calculation())
        with get_conn(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payroll_runs").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT status FROM payroll_runs WHERE id=?", (earlier_id,)
            ).fetchone()[0], "Paid")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payroll_items").fetchone()[0], 1)

    def test_valid_earlier_paid_month_snapshots_do_not_block_later_draft(self) -> None:
        earlier_id = self.draft(
            self.calculation(gross=1000, sss=50),
            start=date(2026, 6, 1), end=date(2026, 6, 14)
        )
        with get_conn(self.db) as conn:
            conn.execute("UPDATE payroll_runs SET status='Paid' WHERE id=?", (earlier_id,))
            conn.commit()
        new_id = self.draft(self.calculation(gross=2000, sss=100))
        self.assertEqual(self.snapshots(new_id), [("2026-06-01", 2000.0, 100.0)])
        self.assertEqual(self.snapshots(earlier_id), [("2026-06-01", 1000.0, 50.0)])

    def test_cross_month_earlier_missing_history_blocks_only_affected_month(self) -> None:
        earlier_id = self.draft(
            self.calculation(), start=date(2026, 6, 15), end=date(2026, 6, 29)
        )
        with get_conn(self.db) as conn:
            conn.execute("UPDATE payroll_runs SET status='Paid' WHERE id=?", (earlier_id,))
            conn.execute("DELETE FROM payroll_statutory_months WHERE payroll_run_id=?", (earlier_id,))
            conn.commit()

        july_result = self.calculation(by_month={
            date(2026, 6, 1): {"gross_pay": 50},
            date(2026, 7, 1): {"gross_pay": 1950, "sss_ee": 100},
        })
        with self.assertRaisesRegex(ValueError, "2026-06"):
            self.draft(
                july_result, start=date(2026, 6, 30),
                end=date(2026, 7, 14), label="Manual cross-month",
            )

    def test_paid_run_guard_preserves_existing_snapshot(self) -> None:
        run_id = self.draft(self.calculation())
        with get_conn(self.db) as conn:
            conn.execute("UPDATE payroll_runs SET status='Paid' WHERE id=?", (run_id,))
            conn.commit()
            with self.assertRaisesRegex(ValueError, "Draft payroll run"):
                persist_computed_draft_snapshots(
                    conn, run_id, self.calculation(gross=3000, sss=125),
                    "2026-06-15", "2026-06-29",
                )
        self.assertEqual(self.snapshots(run_id), [("2026-06-01", 2000.0, 100.0)])

    def test_snapshot_money_mismatch_fails_without_partial_replacement(self) -> None:
        run_id = self.draft(self.calculation())
        incorrect = self.calculation(gross=3000, sss=125)
        incorrect._statutory_snapshots[date(2026, 6, 1)]["sss_ee"] = 100
        with get_conn(self.db) as conn:
            with self.assertRaisesRegex(ValueError, "does not reconcile"):
                persist_computed_draft_snapshots(
                    conn, run_id, incorrect, "2026-06-15", "2026-06-29"
                )
        self.assertEqual(self.snapshots(run_id), [("2026-06-01", 2000.0, 100.0)])


if __name__ == "__main__":
    unittest.main()
