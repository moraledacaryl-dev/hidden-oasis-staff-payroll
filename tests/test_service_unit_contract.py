from __future__ import annotations

import unittest
from pathlib import Path


class ServiceUnitContractTests(unittest.TestCase):
    def test_api_is_loopback_only(self) -> None:
        source = Path(
            "deployment/staff-payroll-api.service"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "--host 127.0.0.1 --port 8001",
            source,
        )
        self.assertNotIn("--host 0.0.0.0", source)

    def test_web_is_loopback_only(self) -> None:
        source = Path(
            "deployment/staff-payroll-web.service"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "--hostname 127.0.0.1 --port 3001",
            source,
        )
        self.assertNotIn("--hostname 0.0.0.0", source)

    def test_services_retain_systemd_hardening(self) -> None:
        for filename in (
            "deployment/staff-payroll-api.service",
            "deployment/staff-payroll-web.service",
        ):
            source = Path(filename).read_text(
                encoding="utf-8"
            )

            self.assertIn("NoNewPrivileges=yes", source)
            self.assertIn("PrivateTmp=yes", source)
            self.assertIn("ProtectSystem=full", source)
            self.assertIn("CapabilityBoundingSet=", source)


if __name__ == "__main__":
    unittest.main()
