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

    def test_post_switch_commands_explicitly_rollback_on_failure(self) -> None:
        source = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")

        switch = source.index('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"')
        post_switch = source[switch:]

        self.assertIn(
            'if ! install -m 0644 "$APP_ROOT/deployment/$WEB_SERVICE" "$WEB_UNIT_PATH"; then\n  rollback 1\nfi',
            post_switch,
        )
        self.assertIn(
            'if ! systemctl daemon-reload; then\n  rollback 1\nfi',
            post_switch,
        )
        self.assertIn(
            'if ! systemctl start "$API_SERVICE"; then\n  rollback 1\nfi',
            post_switch,
        )
        self.assertIn(
            'if ! systemctl start "$WEB_SERVICE"; then\n  rollback 1\nfi',
            post_switch,
        )
        self.assertIn(
            'if ! systemctl start "$WORKER_SERVICE"; then\n  rollback 1\nfi',
            post_switch,
        )

    def test_activation_fences_legacy_web_restarts_before_standalone_start(self) -> None:
        source = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")

        quiesce_start = source.index("quiesce_old_runtime() {")
        quiesce_end = source.index("runtime_ready() {", quiesce_start)
        quiesce = source[quiesce_start:quiesce_end]

        self.assertIn('systemctl stop "$WEB_SERVICE"', quiesce)
        self.assertIn("mask_web_runtime", quiesce)
        self.assertIn("wait_port_stably_free 3001", quiesce)

        switch = source.index('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"')
        start_web = source.index('if ! systemctl start "$WEB_SERVICE"; then', switch)
        pre_start = source[switch:start_web]

        self.assertIn("unmask_web_runtime", pre_start)
        self.assertIn("kill_listener 3001", pre_start)
        self.assertIn("wait_port_stably_free 3001", pre_start)

        rollback_start = source.index("rollback() {")
        rollback_end = source.index("[[ \"$(id -u)\" == \"0\" ]]", rollback_start)
        rollback = source[rollback_start:rollback_end]
        self.assertIn("unmask_web_runtime", rollback)

    def test_production_deploy_delegates_cutover_to_canonical_activator(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")

        self.assertIn('bash "$APP_ROOT/scripts/activate_staged_release.sh"', source)
        self.assertNotIn('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"', source)
        self.assertNotIn('ln -sfn "$RELEASE_DIR" "$RUNTIME_BASE/.current.new"', source)
        self.assertNotIn("quiesce_runtime() {", source)
        self.assertIn('[[ "$(readlink -f "$CURRENT_LINK")" == "$RELEASE_DIR" ]]', source)
        self.assertIn('[[ "$(cat "$DEPLOY_STATE_FILE")" == "$CURRENT_COMMIT" ]]', source)
        self.assertIn('verify_listener_owner "$API_SERVICE" 8001', source)
        self.assertIn('verify_listener_owner "$WEB_SERVICE" 3001', source)


if __name__ == "__main__":
    unittest.main()
