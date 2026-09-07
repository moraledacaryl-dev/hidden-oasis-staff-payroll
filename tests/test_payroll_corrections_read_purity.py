from __future__ import annotations

import inspect
import unittest

from api import payroll_corrections, server


class PayrollCorrectionsReadPurityTests(unittest.TestCase):
    def test_corrections_get_does_not_initialize_schema_or_commit(self) -> None:
        source = inspect.getsource(payroll_corrections.list_payroll_corrections)
        self.assertNotIn("ensure_payroll_corrections_schema", source)
        self.assertNotIn("conn.commit()", source)

    def test_correction_write_handlers_keep_defensive_schema_initialization(self) -> None:
        for handler in (
            payroll_corrections.create_payroll_correction,
            payroll_corrections.void_payroll_correction,
        ):
            with self.subTest(handler=handler.__name__):
                source = inspect.getsource(handler)
                self.assertIn("ensure_payroll_corrections_schema(conn)", source)

    def test_runtime_startup_owns_payroll_corrections_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_payroll_corrections_schema(conn)", source)


if __name__ == "__main__":
    unittest.main()
