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

    def test_all_services_retain_systemd_hardening_and_umask(self) -> None:
        for filename in (
            "deployment/staff-payroll-api.service",
            "deployment/staff-payroll-web.service",
            "deployment/hiddenoasis-staff-integration-worker.service",
        ):
            source = Path(filename).read_text(encoding="utf-8")
            self.assertIn("UMask=0077", source)
            self.assertIn("NoNewPrivileges=yes", source)
            self.assertIn("PrivateTmp=yes", source)
            self.assertIn("ProtectSystem=full", source)
            self.assertIn("ProtectHome=read-only", source)
            self.assertIn("CapabilityBoundingSet=", source)

    def test_worker_uses_canonical_checkout(self) -> None:
        source = Path(
            "deployment/hiddenoasis-staff-integration-worker.service"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "WorkingDirectory=/root/repos/hidden-oasis-staff-payroll",
            source,
        )
        self.assertIn(
            "/root/repos/hidden-oasis-staff-payroll/.venv-api/bin/python",
            source,
        )
        self.assertIn(
            "After=network-online.target staff-payroll-api.service",
            source,
        )
        self.assertNotIn(
            "/opt/hidden-oasis-staff-payroll",
            source,
        )

    def test_deploy_script_uses_canonical_names_and_worker(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'APP_ENV="${APP_ENV:-/etc/hiddenoasis/staff-payroll.env}"',
            source,
        )
        self.assertIn(
            'API_SERVICE="${API_SERVICE:-staff-payroll-api.service}"',
            source,
        )
        self.assertIn(
            'WEB_SERVICE="${WEB_SERVICE:-staff-payroll-web.service}"',
            source,
        )
        self.assertIn(
            'WORKER_SERVICE="${WORKER_SERVICE:-hiddenoasis-staff-integration-worker.service}"',
            source,
        )
        self.assertIn('systemctl restart "$WORKER_SERVICE"', source)
        self.assertIn('verify_service_active "$WORKER_SERVICE"', source)
        self.assertNotIn("hidden-oasis-payroll-api", source)
        self.assertNotIn("hidden-oasis-payroll-web", source)
        self.assertNotIn("/etc/hidden-oasis-payroll/app.env", source)

    def test_deploy_script_verifies_listener_ownership(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('verify_listener_owner "$API_SERVICE" 8001', source)
        self.assertIn('verify_listener_owner "$WEB_SERVICE" 3001', source)
        self.assertIn("MainPID", source)
        self.assertIn("ss -ltnp", source)

    def test_deploy_script_does_not_destructively_reset_git(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("git reset --hard", source)
        self.assertIn("working tree is dirty; refusing production deployment", source)


if __name__ == "__main__":
    unittest.main()
