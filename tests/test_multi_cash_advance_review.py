from __future__ import annotations

import unittest
from unittest.mock import patch

from api.payroll_review_aggregate import normalize_cash_advance_run_check


class MultiCashAdvanceReviewTests(unittest.TestCase):
    def test_draft_review_allocates_full_employee_deduction_fifo(self) -> None:
        result = {
            "source": "current_run_deductions",
            "rows": [
                {
                    "employee_id": 13,
                    "cash_advance_id": 101,
                    "balance_before_run": 100.0,
                    "applied": 50.0,
                    "expected": 50.0,
                    "balance_after_run": 50.0,
                    "status": "APPLIED",
                    "repayment_method": "Payroll deduction",
                },
                {
                    "employee_id": 13,
                    "cash_advance_id": 102,
                    "balance_before_run": 200.0,
                    "applied": 50.0,
                    "expected": 50.0,
                    "balance_after_run": 150.0,
                    "status": "APPLIED",
                    "repayment_method": "Payroll deduction",
                },
            ],
        }

        def fake_fetchall(_conn, sql, _params):
            if "FROM payroll_items" in sql:
                return [{"employee_id": 13, "deduction": 250.0}]
            if "FROM payroll_item_adjustments" in sql:
                return []
            raise AssertionError(sql)

        with patch("api.payroll_review_aggregate.fetchall", side_effect=fake_fetchall):
            normalized = normalize_cash_advance_run_check(object(), 77, result)

        self.assertEqual([100.0, 150.0], [row["applied"] for row in normalized["rows"]])
        self.assertEqual([0.0, 50.0], [row["balance_after_run"] for row in normalized["rows"]])
        self.assertEqual(250.0, normalized["applied_total"])
        self.assertEqual(250.0, normalized["expected_total"])
        self.assertEqual(0, normalized["issue_count"])
        self.assertEqual("OK", normalized["status"])

    def test_paid_review_accepts_posted_multi_advance_allocation_and_ignores_unused_later_advance(self) -> None:
        result = {
            "source": "posted_repayments",
            "rows": [
                {
                    "employee_id": 13,
                    "cash_advance_id": 101,
                    "applied": 100.0,
                    "expected": 50.0,
                    "status": "OVER",
                    "repayment_method": "Payroll deduction",
                },
                {
                    "employee_id": 13,
                    "cash_advance_id": 102,
                    "applied": 150.0,
                    "expected": 50.0,
                    "status": "OVER",
                    "repayment_method": "Payroll deduction",
                },
                {
                    "employee_id": 13,
                    "cash_advance_id": 103,
                    "applied": 0.0,
                    "expected": 0.0,
                    "status": "NOT APPLIED",
                    "repayment_method": "Payroll deduction",
                },
            ],
        }

        with patch(
            "api.payroll_review_aggregate.fetchall",
            return_value=[{"employee_id": 13, "deduction": 250.0}],
        ):
            normalized = normalize_cash_advance_run_check(object(), 77, result)

        self.assertEqual(["APPLIED", "APPLIED", "NOT SELECTED"], [row["status"] for row in normalized["rows"]])
        self.assertEqual([100.0, 150.0, 0.0], [row["expected"] for row in normalized["rows"]])
        self.assertEqual(250.0, normalized["applied_total"])
        self.assertEqual(250.0, normalized["expected_total"])
        self.assertEqual(0, normalized["issue_count"])
        self.assertEqual("OK", normalized["status"])

    def test_paid_review_flags_when_posted_repayments_do_not_match_payroll_item(self) -> None:
        result = {
            "source": "posted_repayments",
            "rows": [
                {
                    "employee_id": 13,
                    "cash_advance_id": 101,
                    "applied": 100.0,
                    "expected": 100.0,
                    "status": "APPLIED",
                    "repayment_method": "Payroll deduction",
                }
            ],
        }

        with patch(
            "api.payroll_review_aggregate.fetchall",
            return_value=[{"employee_id": 13, "deduction": 250.0}],
        ):
            normalized = normalize_cash_advance_run_check(object(), 77, result)

        self.assertEqual("PARTIAL", normalized["rows"][0]["status"])
        self.assertEqual(1, normalized["issue_count"])
        self.assertEqual("Needs Review", normalized["status"])


if __name__ == "__main__":
    unittest.main()
