from __future__ import annotations

import unittest

from core.active_employee_status import is_active_employee_status


class ActiveEmployeeStatusTests(unittest.TestCase):
    def test_separation_statuses_are_inactive(self) -> None:
        for status in ("Inactive", "Terminated", "Resigned", "Separated"):
            with self.subTest(status=status):
                self.assertFalse(is_active_employee_status(status))

    def test_active_and_on_leave_remain_eligible(self) -> None:
        self.assertTrue(is_active_employee_status("Active"))
        self.assertTrue(is_active_employee_status("On Leave"))


if __name__ == "__main__":
    unittest.main()
