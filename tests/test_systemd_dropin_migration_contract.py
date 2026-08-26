from __future__ import annotations

import unittest
from pathlib import Path


class SystemdDropinMigrationContractTests(unittest.TestCase):
    def test_wrapper_backs_up_removes_and_restores_dropins(self) -> None:
        source = Path(
            "scripts/cutover_nonroot_runtime_clean.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("MIGRATION_BACKUP", source)
        self.assertIn('cp -a "$dropin_dir" "$MIGRATION_BACKUP/$service.d"', source)
        self.assertGreaterEqual(
            source.count('rm -rf "/etc/systemd/system/$service.d"'),
            1,
        )
        self.assertIn("restore_complete_pre_migration_state()", source)
        self.assertIn(
            'cp -a "$MIGRATION_BACKUP/$service.d" "$dropin_dir"',
            source,
        )
        self.assertIn("systemctl daemon-reload", source)

    def test_wrapper_verifies_effective_nonroot_unit_configuration(self) -> None:
        source = Path(
            "scripts/cutover_nonroot_runtime_clean.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('bash scripts/cutover_nonroot_runtime.sh', source)
        self.assertIn('systemctl show "$service" -p DropInPaths --value', source)
        self.assertIn('systemctl show "$service" -p User --value', source)
        self.assertIn('systemctl show "$service" -p WorkingDirectory --value', source)
        self.assertIn('systemctl show "$service" -p ExecStart --value', source)
        self.assertIn('[[ "$user" == "staff-payroll" ]]', source)
        self.assertIn(
            '[[ "$working_dir" == /opt/hiddenoasis/staff-payroll/current* ]]',
            source,
        )
        self.assertIn(
            '[[ "$exec_start" == *"/opt/hiddenoasis/staff-payroll/current"* ]]',
            source,
        )
        self.assertIn('[[ -z "$dropins" ]]', source)

    def test_wrapper_fully_quiesces_legacy_runtime_before_cutover_and_rollback(self) -> None:
        source = Path(
            "scripts/cutover_nonroot_runtime_clean.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("quiesce_runtime()", source)
        self.assertIn(
            'systemctl kill --kill-who=all --signal=SIGKILL "$WEB_SERVICE"',
            source,
        )
        self.assertIn(
            'systemctl kill --kill-who=all --signal=SIGKILL "$API_SERVICE"',
            source,
        )
        self.assertIn("wait_port_stably_free()", source)
        self.assertIn('wait_port_stably_free 3001', source)
        self.assertIn('wait_port_stably_free 8001', source)
        self.assertGreaterEqual(source.count("quiesce_runtime"), 3)


if __name__ == "__main__":
    unittest.main()
