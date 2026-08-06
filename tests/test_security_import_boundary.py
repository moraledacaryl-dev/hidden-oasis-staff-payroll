from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECURITY_NAMES = {
    "IMPERSONATION_TTL_SECONDS",
    "ROLE_OWNER",
    "ROLE_PAYROLL",
    "ROLE_SUPERVISOR",
    "ROLE_STAFF",
    "current_user_from_token",
    "public_user",
    "require_api_key",
    "require_authenticated_user",
    "require_roles",
    "role_to_key",
    "session_users_from_payload",
    "sign_payload",
    "verify_token",
}
MIGRATED_MODULES = {
    "server.py": {"ROLE_OWNER", "ROLE_PAYROLL", "require_api_key", "require_roles"},
    "impersonation.py": {
        "IMPERSONATION_TTL_SECONDS",
        "current_user_from_token",
        "public_user",
        "require_api_key",
        "role_to_key",
        "sign_payload",
    },
}


def security_imports(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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

    return imported_from_security, imported_from_main


class SecurityImportBoundaryTests(unittest.TestCase):
    def test_migrated_modules_use_security_boundary(self) -> None:
        for filename, expected in MIGRATED_MODULES.items():
            path = ROOT / "api" / filename
            imported_from_security, imported_from_main = security_imports(path)
            self.assertTrue(expected <= imported_from_security, filename)
            self.assertEqual(imported_from_main & SECURITY_NAMES, set(), filename)


if __name__ == "__main__":
    unittest.main()
