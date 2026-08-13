from __future__ import annotations

import unittest
from pathlib import Path


class WebCsrfGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Path(
            "apps/web/middleware.ts"
        ).read_text(encoding="utf-8")

    def test_guard_applies_to_web_api_routes(self) -> None:
        self.assertIn(
            'matcher: ["/api/:path*"]',
            self.source,
        )

    def test_safe_methods_are_explicitly_exempt(self) -> None:
        for method in ("GET", "HEAD", "OPTIONS"):
            self.assertIn(
                f'"{method}"',
                self.source,
            )

    def test_cross_site_fetch_metadata_is_rejected(self) -> None:
        self.assertIn(
            'fetchSite === "cross-site"',
            self.source,
        )
        self.assertIn(
            "status: 403",
            self.source,
        )

    def test_origin_is_compared_to_request_host(self) -> None:
        self.assertIn(
            "suppliedHost !== expectedHost",
            self.source,
        )

    def test_internal_requests_without_origin_remain_supported(self) -> None:
        self.assertIn(
            "if (!origin)",
            self.source,
        )
        self.assertIn(
            "return NextResponse.next()",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
