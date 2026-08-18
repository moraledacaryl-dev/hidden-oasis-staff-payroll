from __future__ import annotations

import unittest
from pathlib import Path


class IntegrationWorkerEntrypointContractTests(unittest.TestCase):
    def test_direct_script_bootstraps_repository_root_before_package_imports(self) -> None:
        source = Path("scripts/run_integration_worker.py").read_text(encoding="utf-8")

        root_index = source.index("PROJECT_ROOT = Path(__file__).resolve().parents[1]")
        path_index = source.index("sys.path.insert(0, str(PROJECT_ROOT))")
        api_index = source.index("from api.main import configured_db_path")
        core_index = source.index("from core.db import get_conn")

        self.assertLess(root_index, api_index)
        self.assertLess(path_index, api_index)
        self.assertLess(path_index, core_index)

    def test_worker_unit_still_executes_direct_script(self) -> None:
        source = Path(
            "deployment/hiddenoasis-staff-integration-worker.service"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "ExecStart=/root/repos/hidden-oasis-staff-payroll/.venv-api/bin/python scripts/run_integration_worker.py",
            source,
        )


if __name__ == "__main__":
    unittest.main()
