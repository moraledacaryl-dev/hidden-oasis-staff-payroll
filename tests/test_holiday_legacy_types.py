import unittest

from api.holidays import _row


class HolidayLegacyTypeTests(unittest.TestCase):
    def test_recognized_legacy_holiday_types_are_normalized_for_editor(self) -> None:
        regular = _row({
            "id": 1,
            "holiday_date": "2026-08-31",
            "name": "Legacy regular",
            "holiday_type": "Regular",
            "active": 1,
            "notes": None,
            "created_at": "2026-01-01 00:00:00",
        })
        special = _row({
            "id": 2,
            "holiday_date": "2026-08-21",
            "name": "Legacy special",
            "holiday_type": "Special",
            "active": 1,
            "notes": None,
            "created_at": "2026-01-01 00:00:00",
        })

        self.assertEqual(regular["holiday_type"], "Regular Holiday")
        self.assertEqual(special["holiday_type"], "Special Non-Working Day")


if __name__ == "__main__":
    unittest.main()
