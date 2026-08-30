from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SecurityHeaderContractTests(unittest.TestCase):
    def test_next_disables_framework_disclosure_and_sets_csp(self) -> None:
        source = (ROOT / "apps" / "web" / "next.config.ts").read_text()
        self.assertIn("poweredByHeader: false", source)
        self.assertIn('key: "Content-Security-Policy"', source)
        self.assertIn("default-src 'self'", source)
        self.assertIn("frame-ancestors 'none'", source)
        self.assertIn("object-src 'none'", source)
        self.assertIn("img-src 'self' data: blob:", source)
        self.assertIn("connect-src 'self'", source)
        self.assertIn("form-action 'self'", source)

    def test_existing_browser_security_headers_remain(self) -> None:
        source = (ROOT / "apps" / "web" / "next.config.ts").read_text()
        for header in (
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
            "Cross-Origin-Opener-Policy",
            "Cross-Origin-Resource-Policy",
        ):
            self.assertIn(header, source)

    def test_edge_ownership_is_documented(self) -> None:
        docs = (ROOT / "docs" / "security-header-ownership.md").read_text()
        self.assertIn("Nginx public HTTPS edge", docs)
        self.assertIn("Strict-Transport-Security", docs)
        self.assertIn("staff.hiddenoasis.app", docs)
        self.assertIn("X-Powered-By", docs)
        self.assertIn("Content-Security-Policy", docs)


if __name__ == "__main__":
    unittest.main()
