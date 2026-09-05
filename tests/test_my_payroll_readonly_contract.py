from __future__ import annotations

import unittest
from pathlib import Path


class MyPayrollReadonlyContractTests(unittest.TestCase):
    def test_staff_payroll_get_does_not_mutate_schema_or_commit(self) -> None:
        source = Path("api/my_payroll.py").read_text(encoding="utf-8")

        self.assertNotIn("ALTER TABLE", source)
        self.assertNotIn("ensure_user_employee_column", source)
        self.assertNotIn("conn.commit()", source)

    def test_startup_database_contract_owns_user_employee_column(self) -> None:
        source = Path("core/db.py").read_text(encoding="utf-8")

        self.assertIn(
            'ensure_column(conn, "app_users", "employee_id", "INTEGER")',
            source,
        )


if __name__ == "__main__":
    unittest.main()
