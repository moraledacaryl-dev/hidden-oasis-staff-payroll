from __future__ import annotations

import unittest
from pathlib import Path


class PrivilegedMfaReenrollmentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = Path("api/users.py").read_text(encoding="utf-8")
        self.ui = Path("apps/web/components/MfaSettingsForm.tsx").read_text(encoding="utf-8")
        self.page = Path("apps/web/app/settings/security/page.tsx").read_text(encoding="utf-8")

    def test_replacement_uses_pending_enrollment_not_active_secret(self) -> None:
        self.assertIn("mfa_pending_enrollments", self.backend)
        self.assertIn("INSERT INTO mfa_pending_enrollments", self.backend)
        self.assertIn("encrypted_secret=excluded.encrypted_secret", self.backend)

    def test_confirm_promotes_pending_secret_and_revokes_old_sessions(self) -> None:
        self.assertIn("SELECT * FROM mfa_pending_enrollments WHERE user_id=?", self.backend)
        self.assertIn("SET mfa_secret=?,", self.backend)
        self.assertIn("session_version=COALESCE(session_version,1)+1", self.backend)
        self.assertIn("DELETE FROM mfa_pending_enrollments WHERE user_id=?", self.backend)

    def test_privileged_disable_is_rejected(self) -> None:
        self.assertIn("if privileged_mfa_enforced(row):", self.backend)
        self.assertIn("Privileged accounts cannot disable MFA in production", self.backend)

    def test_privileged_ui_offers_replace_instead_of_disable(self) -> None:
        self.assertIn("privilegedMfaRequired", self.ui)
        self.assertIn("Replace authenticator", self.ui)
        self.assertIn("!privilegedMfaRequired", self.ui)
        self.assertIn("Disable authenticator", self.ui)

    def test_settings_page_derives_privileged_policy(self) -> None:
        self.assertIn('session?.role_key === "owner"', self.page)
        self.assertIn('session?.role_key === "payroll"', self.page)
        self.assertIn("STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA", self.page)

    def test_replacement_copy_promises_old_factor_remains_active(self) -> None:
        self.assertIn("existing authenticator remains valid until this replacement is confirmed", self.ui)


if __name__ == "__main__":
    unittest.main()
