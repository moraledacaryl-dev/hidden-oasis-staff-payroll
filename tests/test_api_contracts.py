from __future__ import annotations

import unittest
from pathlib import Path

from api.server import app
from api.users import normalized_role


class ApiContractTests(unittest.TestCase):
    def test_current_contract_contains_required_routes(self):
        paths = app.openapi()["paths"]
        required = {
            "/api/v1/auth/login",
            "/api/v1/auth/change-password",
            "/api/v1/auth/mfa/setup",
            "/api/v1/auth/impersonate",
            "/api/v1/auth/impersonate/end",
            "/api/v1/users",
            "/api/v1/staff/employees",
            "/api/v1/schedules/shifts",
            "/api/v1/schedules/shifts/{shift_id}/move",
            "/api/v1/schedules/shifts/{shift_id}/duplicate",
            "/api/v1/schedule/change-requests/{request_id}/decision",
            "/api/v1/me/published-self-service",
            "/api/v1/me/leave-requests",
            "/api/v1/hr/leave-requests/{request_id}/decision",
            "/api/v1/production/backups",
            "/api/v1/payroll/runs",
        }
        self.assertTrue(required.issubset(paths), required - set(paths))

    def test_openapi_operation_ids_are_unique(self):
        operation_ids: list[str] = []
        for methods in app.openapi()["paths"].values():
            for operation in methods.values():
                if isinstance(operation, dict) and operation.get("operationId"):
                    operation_ids.append(str(operation["operationId"]))
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_versioned_python_modules_are_removed(self):
        api_dir = Path(__file__).resolve().parents[1] / "api"
        versioned = sorted(path.name for path in api_dir.glob("*_v[0-9]*.py"))
        self.assertEqual(versioned, [])

    def test_general_manager_alias_keeps_stable_role_key(self):
        self.assertEqual(normalized_role("General Manager"), ("supervisor", "General Manager"))
        self.assertEqual(normalized_role("supervisor"), ("supervisor", "General Manager"))


if __name__ == "__main__":
    unittest.main()
