from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "api" / "server.py"
SECURITY_NAMES = {
    "ROLE_OWNER",
    "ROLE_PAYROLL",
    "ROLE_SUPERVISOR",
    "ROLE_STAFF",
    "current_user_from_token",
    "require_api_key",
    "require_authenticated_user",
    "require_roles",
    "role_to_key",
    "session_users_from_payload",
    "sign_payload",
    "verify_token",
}


class SecurityImportBoundaryTests(unittest.TestCase):
    def test_server_imports_security_symbols_from_boundary(self) -> None:
        tree = ast.parse(SERVER.read_text(encoding="utf-8"), filename=str(SERVER))
        imported_from_security: set[str] = set()
        imported_from_main: set[str] = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            names = {alias.name for alias in node.names}
            if node.module == "api.security":
                imported_from_security.update(names)
            elif node.module == "api.main":
                imported_from_main.update(names)

        self.assertTrue(
            {"ROLE_OWNER", "ROLE_PAYROLL", "require_api_key", "require_roles"}
            <= imported_from_security
        )
        self.assertEqual(imported_from_main & SECURITY_NAMES, set())


if __name__ == "__main__":
    unittest.main()
