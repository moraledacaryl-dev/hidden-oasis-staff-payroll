from __future__ import annotations

import unittest

from core.active_employee_status import INACTIVE_EMPLOYEE_STATUSES


class SeparatedEmployeeStatusSourceContractTests(unittest.TestCase):
    def test_all_terminal_statuses_share_one_policy(self) -> None:
        self.assertEqual(
            INACTIVE_EMPLOYEE_STATUSES,
            frozenset({"inactive", "terminated", "resigned", "separated"}),
        )


if __name__ == "__main__":
    unittest.main()
