from __future__ import annotations

import inspect
import sqlite3
import unittest

import api.hr_records as hr_records
from api import server


class HrReadonlyContractTests(unittest.TestCase):
    def test_leave_balance_get_is_side_effect_free(self) -> None:
        source = inspect.getsource(hr_records.leave_balances)
        self.assertNotIn("ensure_schema(conn)", source)
        self.assertNotIn("sync_entitlement_usage", source)
        self.assertNotIn("conn.commit()", source)
        self.assertIn("leave_request_used_days", source)

    def test_other_hr_gets_do_not_initialize_schema(self) -> None:
        for handler in (hr_records.list_leave_requests, hr_records.hr_records):
            source = inspect.getsource(handler)
            self.assertNotIn("ensure_schema(conn)", source)
            self.assertNotIn("conn.commit()", source)

    def test_startup_owns_hr_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_hr_schema(conn)", source)

    def test_persistent_usage_sync_remains_write_only_helper(self) -> None:
        source = inspect.getsource(hr_records.sync_entitlement_usage)
        self.assertIn("UPDATE employee_leave_entitlements", source)

    def test_pure_usage_calculation_does_not_change_entitlement_row(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE leave_requests (
                id INTEGER PRIMARY KEY,
                employee_id INTEGER NOT NULL,
                leave_type_id INTEGER,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                days REAL NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE employee_leave_entitlements (
                id INTEGER PRIMARY KEY,
                employee_id INTEGER NOT NULL,
                leave_type_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                used REAL NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            INSERT INTO employee_leave_entitlements
                (id, employee_id, leave_type_id, year, used, updated_at)
            VALUES (1, 7, 2, 2026, 99, 'sentinel');
            INSERT INTO leave_requests
                (id, employee_id, leave_type_id, start_date, end_date, days, status)
            VALUES
                (1, 7, 2, '2026-03-01', '2026-03-02', 2, 'Approved'),
                (2, 7, 2, '2026-04-01', '2026-04-01', 1, 'Rejected');
            """
        )
        used = hr_records.leave_request_used_days(
            conn, 7, 2, "2026-01-01", "2026-12-31"
        )
        row = conn.execute(
            "SELECT used, updated_at FROM employee_leave_entitlements WHERE id=1"
        ).fetchone()
        self.assertEqual(used, 2.0)
        self.assertEqual(float(row["used"]), 99.0)
        self.assertEqual(row["updated_at"], "sentinel")
        conn.close()


if __name__ == "__main__":
    unittest.main()
