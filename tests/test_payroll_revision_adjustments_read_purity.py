from __future__ import annotations

import inspect
import unittest

from api import payroll_revision_workflow, server


class PayrollRevisionAdjustmentsReadPurityTests(unittest.TestCase):
    def test_revision_adjustments_get_does_not_initialize_workflow_schema(self) -> None:
        source = inspect.getsource(payroll_revision_workflow.get_revision_adjustments)
        self.assertNotIn("ensure_workflow_schema", source)

    def test_controlled_revision_write_keeps_defensive_workflow_schema(self) -> None:
        source = inspect.getsource(payroll_revision_workflow.save_controlled_revision)
        self.assertIn("ensure_workflow_schema(conn)", source)

    def test_runtime_startup_owns_revision_workflow_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_workflow_schema(conn)", source)


if __name__ == "__main__":
    unittest.main()
