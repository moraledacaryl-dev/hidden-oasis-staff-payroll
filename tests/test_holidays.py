from __future__ import annotations

import sqlite3
import unittest

from pydantic import ValidationError

from api.holidays import HolidayPayload
from core.payroll_engine import day_pay_multipliers, overtime_multiplier


class HolidayPayrollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE holidays (id INTEGER PRIMARY KEY, holiday_date TEXT UNIQUE, name TEXT, holiday_type TEXT, active INTEGER, notes TEXT, created_at TEXT);
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
            """
        )
        settings = {
            "regular_holiday_multiplier": "2.00",
            "special_holiday_multiplier": "1.30",
            "regular_holiday_rest_day_multiplier": "2.60",
            "special_holiday_rest_day_multiplier": "1.50",
            "rest_day_multiplier": "1.30",
            "premium_day_ot_rate": "1.30",
            "ot_rate": "1.25",
        }
        self.conn.executemany("INSERT INTO app_settings VALUES(?,?,?)", [(key, value, "now") for key, value in settings.items()])

    def tearDown(self) -> None:
        self.conn.close()

    def add_holiday(self, day: str, kind: str, active: int = 1) -> None:
        self.conn.execute("INSERT INTO holidays(holiday_date,name,holiday_type,active,created_at) VALUES(?,?,?,?,?)", (day, "Test Holiday", kind, active, "now"))

    def test_regular_holiday_and_rest_day_rates(self) -> None:
        self.add_holiday("2026-08-31", "Regular Holiday")
        self.assertEqual(day_pay_multipliers(self.conn, "2026-08-31", False)[0], 2.0)
        self.assertEqual(day_pay_multipliers(self.conn, "2026-08-31", True)[0], 2.6)
        self.assertEqual(overtime_multiplier(self.conn, 2.0), 2.6)
        self.assertEqual(overtime_multiplier(self.conn, 2.6), 3.38)

    def test_special_non_working_day_and_rest_day_rates(self) -> None:
        self.add_holiday("2026-08-21", "Special Non-Working Day")
        self.assertEqual(day_pay_multipliers(self.conn, "2026-08-21", False)[0], 1.3)
        self.assertEqual(day_pay_multipliers(self.conn, "2026-08-21", True)[0], 1.5)
        self.assertEqual(overtime_multiplier(self.conn, 1.3), 1.69)
        self.assertEqual(overtime_multiplier(self.conn, 1.5), 1.95)

    def test_inactive_holiday_does_not_affect_payroll(self) -> None:
        self.add_holiday("2026-08-21", "Special Non-Working Day", active=0)
        multiplier, label = day_pay_multipliers(self.conn, "2026-08-21", False)
        self.assertEqual(multiplier, 1.0)
        self.assertEqual(label, "Ordinary Day")

    def test_holiday_affects_only_exact_calendar_date(self) -> None:
        self.add_holiday("2026-08-31", "Regular Holiday")
        self.assertEqual(day_pay_multipliers(self.conn, "2026-08-30", False)[0], 1.0)
        self.assertEqual(day_pay_multipliers(self.conn, "2026-08-31", False)[0], 2.0)

    def test_api_rejects_free_form_holiday_types(self) -> None:
        with self.assertRaises(ValidationError):
            HolidayPayload(holiday_date="2026-08-31", name="Bad type", holiday_type="regular-ish")


if __name__ == "__main__":
    unittest.main()
