from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"
SECURITY_NAMES = {
    "IMPERSONATION_TTL_SECONDS",
    "ROLE_OWNER",
    "ROLE_PAYROLL",
    "ROLE_STAFF",
    "ROLE_SUPERVISOR",
    "SESSION_TTL_SECONDS",
    "current_user_from_token",
    "public_user",
    "require_api_key",
    "require_authenticated_user",
    "require_roles",
    "role_to_key",
    "session_users_from_payload",
    "sign_payload",
    "token_secret",
    "verify_token",
}

# Temporary compatibility debt. Remove a path from this set as soon as its
# security imports are migrated to api.security.
ALLOWED_LEGACY_CONSUMERS = {
    "api/staff_self_service.py",
    "api/users.py",
}


def legacy_security_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "api.main":
            imported.update(alias.name for alias in node.names if alias.name in SECURITY_NAMES)
    return imported


class SecurityLegacyAllowlistTests(unittest.TestCase):
    def test_only_explicit_legacy_modules_import_security_from_api_main(self) -> None:
        actual: dict[str, set[str]] = {}
        for path in sorted(API_DIR.glob("*.py")):
            if path.name == "main.py":
                continue
            names = legacy_security_imports(path)
            if names:
                actual[path.relative_to(ROOT).as_posix()] = names

        self.assertEqual(set(actual), ALLOWED_LEGACY_CONSUMERS)
        self.assertEqual(
            actual["api/users.py"],
            {"current_user_from_token", "require_api_key", "role_to_key"},
        )
        self.assertEqual(
            actual["api/staff_self_service.py"],
            {"current_user_from_token", "require_api_key"},
        )


if __name__ == "__main__":
    unittest.main()
