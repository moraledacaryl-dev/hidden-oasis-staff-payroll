from __future__ import annotations

import unittest
from pathlib import Path


class WebSecurityHeaderConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Path(
            "apps/web/next.config.ts"
        ).read_text(encoding="utf-8")

    def test_required_browser_security_headers_are_configured(self) -> None:
        required = {
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
            "Cross-Origin-Opener-Policy",
            "Cross-Origin-Resource-Policy",
        }

        missing = {
            header
            for header in required
            if header not in self.config
        }

        self.assertEqual(
            missing,
            set(),
            f"Missing web security headers: {sorted(missing)}",
        )

    def test_clickjacking_is_denied(self) -> None:
        self.assertIn(
            'value: "DENY"',
            self.config,
        )

    def test_content_sniffing_is_disabled(self) -> None:
        self.assertIn(
            'value: "nosniff"',
            self.config,
        )


if __name__ == "__main__":
    unittest.main()
