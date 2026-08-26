from __future__ import annotations

import unittest
from pathlib import Path


class StandaloneWebRuntimeContractTests(unittest.TestCase):
    def test_standalone_web_runtime_is_transactional(self) -> None:
        next_config = Path("apps/web/next.config.ts").read_text(encoding="utf-8")
        unit = Path("deployment/staff-payroll-web.service").read_text(encoding="utf-8")
        deploy = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")

        self.assertIn('output: "standalone"', next_config)
        self.assertIn(".next/standalone/server.js", unit)
        self.assertIn("Environment=HOSTNAME=127.0.0.1", unit)
        self.assertIn("Environment=PORT=3001", unit)
        self.assertIn("KillMode=control-group", unit)

        self.assertIn("test -f .next/standalone/server.js", deploy)
        self.assertIn("cp -a .next/static .next/standalone/.next/static", deploy)
        self.assertIn('WEB_UNIT_BACKUP="$(mktemp', deploy)
        self.assertIn('install -m 0644 "$APP_ROOT/deployment/$WEB_SERVICE" "$WEB_UNIT_PATH"', deploy)
        self.assertIn('install -m 0644 "$WEB_UNIT_BACKUP" "$WEB_UNIT_PATH"', deploy)
        self.assertIn("wait_rollback_ready", deploy)
        self.assertIn('ExecStart --value)" == *".next/standalone/server.js"*', deploy)


if __name__ == "__main__":
    unittest.main()
