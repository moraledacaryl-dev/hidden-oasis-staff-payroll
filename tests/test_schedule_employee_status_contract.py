from __future__ import annotations

import pathlib
import unittest


class ScheduleEmployeeStatusContractTests(unittest.TestCase):
    def test_schedule_employee_picker_excludes_all_separated_statuses(self) -> None:
        source = pathlib.Path("api/schedules.py").read_text(encoding="utf-8").lower()
        marker = "not in ('inactive', 'terminated', 'resigned', 'separated')"
        self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
