from __future__ import annotations

import unittest
from pathlib import Path


class MfaUxContractTests(unittest.TestCase):
    def test_security_ui_contains_qr_enrollment(self) -> None:
        source = Path(
            "apps/web/components/MfaSettingsForm.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'import QRCode from "qrcode"',
            source,
        )
        self.assertIn(
            "Authenticator setup QR code",
            source,
        )

    def test_recovery_codes_are_explicitly_one_time(self) -> None:
        source = Path(
            "apps/web/components/MfaSettingsForm.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Each code works once",
            source,
        )
        self.assertIn(
            "I saved these codes",
            source,
        )

    def test_security_proxy_supports_regeneration(self) -> None:
        source = Path(
            "apps/web/app/api/settings/security/route.ts"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'action === "regenerate"',
            source,
        )
        self.assertIn(
            "/api/v1/auth/mfa/recovery-codes/regenerate",
            source,
        )

    def test_regeneration_does_not_clear_active_session(self) -> None:
        source = Path(
            "apps/web/app/api/settings/security/route.ts"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '(action === "confirm" || action === "disable")',
            source,
        )


if __name__ == "__main__":
    unittest.main()
