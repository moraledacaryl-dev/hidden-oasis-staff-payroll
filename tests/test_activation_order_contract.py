from __future__ import annotations

import unittest
from pathlib import Path


class ActivationOrderContractTests(unittest.TestCase):
    def test_activation_quiesces_before_switching_current(self) -> None:
        source = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")

        quiesce = source.index("quiesce_old_runtime\n")
        switch = source.index('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"')
        install_unit = source.index('install -m 0644 "$APP_ROOT/deployment/$WEB_SERVICE" "$WEB_UNIT_PATH"')
        start_web = source.index('systemctl start "$WEB_SERVICE"')

        self.assertLess(quiesce, switch)
        self.assertLess(switch, install_unit)
        self.assertLess(install_unit, start_web)
        self.assertIn("wait_port_stably_free 3001", source)
        self.assertIn("wait_port_stably_free 8001", source)
        self.assertIn(".next/standalone/server.js", source)
        self.assertIn("rollback 1", source)
        self.assertIn("Rollback HTTP health restored.", source)


if __name__ == "__main__":
    unittest.main()
