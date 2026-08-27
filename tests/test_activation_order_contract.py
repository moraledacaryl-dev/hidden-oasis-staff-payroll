from __future__ import annotations

import unittest
from pathlib import Path


class ActivationOrderContractTests(unittest.TestCase):
    def test_activation_quiesces_before_switching_current(self) -> None:
        source = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")

        quiesce = source.index("quiesce_old_runtime\n")
        switch = source.index('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"')
        install_unit = source.index('install -m 0644 "$APP_ROOT/deployment/$WEB_SERVICE" "$WEB_UNIT_PATH"')
        start_web = source.index('systemctl start "$WEB_SERVICE"', install_unit)

        self.assertLess(quiesce, switch)
        self.assertLess(switch, install_unit)
        self.assertLess(install_unit, start_web)
        self.assertIn("wait_port_stably_free 3001", source)
        self.assertIn("wait_port_stably_free 8001", source)
        self.assertIn(".next/standalone/server.js", source)
        self.assertIn("rollback 1", source)

    def test_activation_rollback_requires_full_runtime_readiness(self) -> None:
        source = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")

        rollback_start = source.index("rollback() {")
        rollback_end = source.index("[[ \"$(id -u)\" == \"0\" ]]", rollback_start)
        rollback = source[rollback_start:rollback_end]

        self.assertIn("if wait_runtime_ready; then", rollback)
        self.assertIn("Rollback runtime readiness restored.", rollback)
        self.assertIn("rollback failed to restore canonical runtime readiness", rollback)
        self.assertIn('systemctl status "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"', rollback)
        self.assertIn("ss -ltnp", rollback)
        self.assertNotIn("Rollback HTTP health restored.", rollback)


if __name__ == "__main__":
    unittest.main()
