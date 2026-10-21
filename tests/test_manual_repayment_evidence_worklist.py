"""Security and read-only regression tests for manual repayment evidence exports."""
from __future__ import annotations

import csv
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from scripts.export_manual_repayment_evidence_worklist import (
    HEADER, _safe_spreadsheet_cell, build_worklist, export_private_csv,
)


class HistoricalRepaymentEvidenceExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dbpath = Path(self.temp.name) / "staff.sqlite"
        with sqlite3.connect(self.dbpath) as db:
            db.executescript("""
                CREATE TABLE cash_advance_repayments (
                    id INTEGER PRIMARY KEY, cash_advance_id INTEGER,
                    repayment_date TEXT, amount REAL, source TEXT,
                    active INTEGER, payment_method TEXT, method TEXT,
                    reference TEXT
                );
                CREATE TABLE integration_outbox (
                    id INTEGER PRIMARY KEY, status TEXT,
                    destination TEXT, event_type TEXT,
                    external_source TEXT, external_id TEXT
                );
                INSERT INTO cash_advance_repayments VALUES
                    (15,12,'2026-07-02',1000,'Manual',1,'Cash','Cash','SECRET-15'),
                    (29,21,'2026-08-03',500,'Manual',1,'Cash','Cash',NULL),
                    (30,26,'2026-08-15',3000,'Manual',1,'Other','Other','SECRET-30'),
                    (42,22,'2026-09-18',3000,'Manual',1,'Cash','Cash',NULL),
                    (43,11,'2026-09-18',3000,'Manual',1,'Cash','Cash',NULL),
                    (44,11,'2026-09-19',50,'Manual',1,'Cash','Cash',NULL),
                    (45,11,'2026-09-19',100,'Manual',1,'Other','Other',NULL),
                    (46,11,'2026-09-19',10,'Manual',0,'Cash','Cash',NULL),
                    (47,11,'2026-09-19',600,'Payroll',1,'Payroll deduction','Payroll deduction',NULL);
                INSERT INTO integration_outbox VALUES
                    (1,'Completed','accounting','cash_advance.repaid',
                     'hidden_oasis_staff_payroll','cash-advance-repayment:44'),
                    (2,'Completed','accounting','cash_advance.repaid',
                     'hidden_oasis_staff_payroll','cash-advance-repayment:45'),
                    (3,'Completed','pos','cash_advance.repaid',
                     'hidden_oasis_staff_payroll','cash-advance-repayment:15');
            """)

    def _build(self, *, include_all=False):
        with sqlite3.connect(self.dbpath.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            return build_worklist(conn, include_all=include_all)

    def test_default_exports_five_missing_and_one_ambiguous_delivered(self):
        before = self.dbpath.read_bytes()
        rows, summary = self._build()
        self.assertEqual(summary["active_manual_repayment_count"], 7)
        self.assertEqual(summary["exception_count"], 6)
        self.assertEqual(summary["exported_case_count"], 6)
        self.assertEqual(summary["exported_amount_php"], 10600.0)
        self.assertEqual({r["staff_repayment_id"] for r in rows}, {15,29,30,42,43,45})
        self.assertEqual({r["staff_accounting_handoff"] for r in rows},
                         {"missing_staff_outbox", "delivered_posting_unverified"})
        self.assertEqual(rows[0]["staff_amount_php"], "1000.00")
        self.assertEqual(rows[0]["staff_receipt_reference_present"], "YES")
        self.assertEqual(rows[1]["staff_receipt_reference_present"], "NO")
        self.assertEqual(rows[0]["accounting_intake_or_journal_verified"], "NOT_REVIEWED")
        self.assertEqual(rows[0]["reconciliation_decision"], "PENDING_EVIDENCE")
        self.assertNotIn("SECRET", str(rows))
        self.assertFalse(summary["cash_custody_verified_by_this_export"])
        self.assertEqual(summary["financial_postings_or_replays_performed"], 0)
        self.assertEqual(before, self.dbpath.read_bytes())

    def test_all_manual_adds_clean_delivery_but_not_payroll_or_inactive(self):
        rows, summary = self._build(include_all=True)
        self.assertEqual(summary["exported_case_count"], 7)
        self.assertEqual(summary["exported_amount_php"], 10650.0)
        self.assertIn(44, {r["staff_repayment_id"] for r in rows})
        self.assertNotIn(46, {r["staff_repayment_id"] for r in rows})
        self.assertNotIn(47, {r["staff_repayment_id"] for r in rows})

    def test_private_csv_does_not_overwrite_and_has_no_receipt_values(self):
        rows, _ = self._build()
        destination = Path(self.temp.name) / "private-worklist.csv"
        export_private_csv(destination, rows)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        with destination.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(tuple(reader.fieldnames), HEADER)
            content = list(reader)
        self.assertEqual(len(content), 6)
        self.assertEqual(content[0]["staff_repayment_id"], "15")
        self.assertEqual(content[0]["staff_amount_php"], "1000.00")
        self.assertNotIn("SECRET", destination.read_text())
        original_bytes = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            export_private_csv(destination, rows)
        self.assertEqual(destination.read_bytes(), original_bytes)

    def test_spreadsheet_formula_injection_is_neutralized(self):
        for bad in ("=HYPERLINK(1)", "+cmd", "-cmd", "@SUM(1)", "  =evil", chr(9) + "=evil"):
            self.assertTrue(str(_safe_spreadsheet_cell(bad)).startswith("'"))
        self.assertEqual(_safe_spreadsheet_cell("Cash"), "Cash")
        self.assertEqual(_safe_spreadsheet_cell("2026-09-18"), "2026-09-18")

    def test_missing_schema_fails_closed_and_does_not_create_anything(self):
        with sqlite3.connect(self.dbpath) as db:
            db.execute("DROP TABLE integration_outbox")
        with self.assertRaisesRegex(RuntimeError, "missing columns"):
            self._build()
        with self.assertRaises(ValueError):
            export_private_csv(Path("relative.csv"), [])

    def test_review_columns_default_to_unverified_for_every_case(self):
        rows, _ = self._build()
        for row in rows:
            for column in ("original_receipt_verified", "cashbook_or_deposit_verified",
                           "actual_receiving_method_verified",
                           "actual_receiving_account_verified",
                           "accounting_intake_or_journal_verified",
                           "payroll_deduction_conflict_checked",
                           "possible_duplicate_cash_receipt_checked"):
                self.assertEqual(row[column], "NOT_REVIEWED")
            self.assertFalse(row["review_notes"])


if __name__ == "__main__":
    unittest.main()
