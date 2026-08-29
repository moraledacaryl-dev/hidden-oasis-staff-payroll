from __future__ import annotations

import unittest
from pathlib import Path


class ServiceUnitContractTests(unittest.TestCase):
    def test_api_is_loopback_only(self) -> None:
        source = Path(
            "deployment/staff-payroll-api.service"
        ).read_text(encoding="utf-8")
        self.assertIn("--host 127.0.0.1 --port 8001", source)
        self.assertNotIn("--host 0.0.0.0", source)

    def test_web_is_loopback_only(self) -> None:
        source = Path(
            "deployment/staff-payroll-web.service"
        ).read_text(encoding="utf-8")
        self.assertIn("Environment=HOSTNAME=127.0.0.1", source)
        self.assertIn("Environment=PORT=3001", source)
        self.assertIn(".next/standalone/server.js", source)
        self.assertNotIn("HOSTNAME=0.0.0.0", source)

    def test_all_services_run_as_dedicated_user_with_hardening(self) -> None:
        for filename in (
            "deployment/staff-payroll-api.service",
            "deployment/staff-payroll-web.service",
            "deployment/hiddenoasis-staff-integration-worker.service",
        ):
            source = Path(filename).read_text(encoding="utf-8")
            self.assertIn("User=staff-payroll", source)
            self.assertIn("Group=staff-payroll", source)
            self.assertIn("UMask=0077", source)
            self.assertIn("NoNewPrivileges=yes", source)
            self.assertIn("PrivateTmp=yes", source)
            self.assertIn("ProtectSystem=full", source)
            self.assertIn("ProtectHome=yes", source)
            self.assertIn("CapabilityBoundingSet=", source)
            self.assertNotIn("User=root", source)

    def test_services_use_non_root_runtime_release(self) -> None:
        api = Path("deployment/staff-payroll-api.service").read_text(encoding="utf-8")
        web = Path("deployment/staff-payroll-web.service").read_text(encoding="utf-8")
        worker = Path(
            "deployment/hiddenoasis-staff-integration-worker.service"
        ).read_text(encoding="utf-8")

        for source in (api, web, worker):
            self.assertIn("/opt/hiddenoasis/staff-payroll/current", source)
            self.assertNotIn("WorkingDirectory=/root/", source)
            self.assertNotIn("ExecStart=/root/", source)

        self.assertIn(
            "After=network-online.target staff-payroll-api.service",
            worker,
        )
        self.assertIn(
            "ReadWritePaths=/var/lib/hiddenoasis/staff-payroll",
            worker,
        )

    def test_api_writes_only_state_and_runtime_backup_paths(self) -> None:
        source = Path(
            "deployment/staff-payroll-api.service"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ReadWritePaths=/var/lib/hiddenoasis/staff-payroll /var/backups/hidden-oasis-staff-payroll/runtime",
            source,
        )

    def test_web_cache_write_path_is_optional(self) -> None:
        source = Path(
            "deployment/staff-payroll-web.service"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ReadWritePaths=-/opt/hiddenoasis/staff-payroll/current/apps/web/.next/cache",
            source,
        )

    def test_deploy_script_uses_canonical_names_and_worker(self) -> None:
        deploy = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        activator = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")
        self.assertIn(
            'APP_ENV="${APP_ENV:-/etc/hiddenoasis/staff-payroll.env}"',
            deploy,
        )
        self.assertIn(
            'API_SERVICE="${API_SERVICE:-staff-payroll-api.service}"',
            deploy,
        )
        self.assertIn(
            'WEB_SERVICE="${WEB_SERVICE:-staff-payroll-web.service}"',
            deploy,
        )
        self.assertIn(
            'WORKER_SERVICE="${WORKER_SERVICE:-hiddenoasis-staff-integration-worker.service}"',
            deploy,
        )
        self.assertIn('bash "$APP_ROOT/scripts/activate_staged_release.sh"', deploy)
        self.assertIn('systemctl start "$WORKER_SERVICE"', activator)
        self.assertIn('systemctl is-active --quiet "$WORKER_SERVICE"', activator)
        self.assertNotIn("hidden-oasis-payroll-api", deploy)
        self.assertNotIn("hidden-oasis-payroll-web", deploy)
        self.assertNotIn("/etc/hidden-oasis-payroll/app.env", deploy)

    def test_deploy_script_stages_atomic_runtime_release(self) -> None:
        deploy = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        activator = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")
        self.assertIn(
            'RUNTIME_BASE="${RUNTIME_BASE:-/opt/hiddenoasis/staff-payroll}"',
            deploy,
        )
        self.assertIn('RELEASE_DIR="$RELEASES_DIR/$CURRENT_COMMIT"', deploy)
        self.assertIn('mkdir -p "$RELEASE_DIR/data"', deploy)
        self.assertIn('chmod 0750 "$RELEASE_DIR/data"', deploy)
        self.assertIn('bash "$APP_ROOT/scripts/activate_staged_release.sh"', deploy)
        self.assertNotIn('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"', deploy)
        self.assertIn('mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"', activator)
        self.assertIn('mv -Tf "$RUNTIME_BASE/.current.rollback" "$CURRENT_LINK"', activator)
        self.assertNotIn("git reset --hard", deploy)

    def test_deploy_script_verifies_listener_and_runtime_user(self) -> None:
        source = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        self.assertIn('verify_listener_owner "$API_SERVICE" 8001', source)
        self.assertIn('verify_listener_owner "$WEB_SERVICE" 3001', source)
        self.assertIn("MainPID", source)
        self.assertIn("ss -ltnp", source)
        self.assertIn('systemctl show "$API_SERVICE" -p User --value', source)
        self.assertIn('systemctl show "$WORKER_SERVICE" -p User --value', source)

    def test_deploy_script_delegates_quiescence_and_creates_web_cache(self) -> None:
        deploy = Path("scripts/deploy_production.sh").read_text(encoding="utf-8")
        activator = Path("scripts/activate_staged_release.sh").read_text(encoding="utf-8")
        self.assertIn('bash "$APP_ROOT/scripts/activate_staged_release.sh"', deploy)
        self.assertIn(".next/cache", deploy)
        self.assertNotIn("quiesce_runtime()", deploy)
        self.assertIn("quiesce_old_runtime()", activator)
        self.assertIn("wait_port_stably_free()", activator)
        self.assertIn('systemctl kill --kill-who=all --signal=SIGKILL "$WEB_SERVICE"', activator)
        self.assertIn('systemctl kill --kill-who=all --signal=SIGKILL "$API_SERVICE"', activator)
        self.assertIn("wait_port_stably_free 3001", activator)
        self.assertIn("wait_port_stably_free 8001", activator)
        self.assertIn('systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"', activator)

    def test_prepare_script_creates_external_state_paths_without_restart(self) -> None:
        source = Path("scripts/prepare_nonroot_runtime.sh").read_text(encoding="utf-8")
        self.assertIn("useradd", source)
        self.assertIn("/var/lib/hiddenoasis/staff-payroll", source)
        self.assertIn("/var/backups/hidden-oasis-staff-payroll/runtime", source)
        self.assertIn("STAFF_PAYROLL_DB_PATH", source)
        self.assertIn("STAFF_UPLOAD_DIR", source)
        self.assertIn("STAFF_PAYROLL_BACKUP_DIR", source)
        self.assertIn("source_conn.backup(target_conn)", source)
        self.assertNotIn("systemctl restart", source)

    def test_cutover_stops_writers_before_final_copy_and_has_rollback(self) -> None:
        source = Path("scripts/cutover_nonroot_runtime.sh").read_text(encoding="utf-8")
        stop_worker = source.index('systemctl stop "$WORKER_SERVICE"')
        stop_web = source.index('systemctl stop "$WEB_SERVICE"')
        stop_api = source.index('systemctl stop "$API_SERVICE"')
        final_copy = source.index('s.backup(t)')
        self.assertLess(stop_worker, final_copy)
        self.assertLess(stop_web, final_copy)
        self.assertLess(stop_api, final_copy)
        self.assertIn("Cutover failed while running:", source)
        self.assertIn("staff-payroll.env.before", source)
        self.assertIn("systemctl daemon-reload", source)
        self.assertIn('wait_listener_owner "$API_SERVICE" 8001', source)
        self.assertIn('wait_listener_owner "$WEB_SERVICE" 3001', source)
        self.assertIn("PRAGMA integrity_check", source)

    def test_cutover_handles_legacy_data_dir_and_first_activation_rollback(self) -> None:
        source = Path("scripts/cutover_nonroot_runtime.sh").read_text(encoding="utf-8")
        self.assertIn('mkdir -p "$RELEASE_DIR/data"', source)
        self.assertIn('chown root:"$SERVICE_GROUP" "$RELEASE_DIR/data"', source)
        self.assertIn('chmod 0750 "$RELEASE_DIR/data"', source)
        self.assertIn('rm -f "$CURRENT_LINK"', source)

    def test_cutover_polls_readiness_and_emits_failure_diagnostics(self) -> None:
        source = Path("scripts/cutover_nonroot_runtime.sh").read_text(encoding="utf-8")
        self.assertIn('READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-45}"', source)
        self.assertIn("wait_service_active()", source)
        self.assertIn("wait_listener_owner()", source)
        self.assertIn("wait_http()", source)
        self.assertIn('wait_service_active "$API_SERVICE"', source)
        self.assertIn('wait_service_active "$WEB_SERVICE"', source)
        self.assertIn('wait_service_active "$WORKER_SERVICE"', source)
        self.assertIn('wait_http "API" "http://127.0.0.1:8001/health"', source)
        self.assertIn('wait_http "web" "http://127.0.0.1:3001/login"', source)
        self.assertIn("Cutover-window service diagnostics before rollback", source)
        self.assertIn('journalctl -u "$unit" --since "$CUTOVER_STARTED_AT"', source)
        self.assertNotIn("sleep 3", source)

    def test_cutover_clears_stale_listeners_forward_and_rollback(self) -> None:
        source = Path("scripts/cutover_nonroot_runtime.sh").read_text(encoding="utf-8")
        self.assertIn("clear_listener_after_stop()", source)
        self.assertGreaterEqual(
            source.count('clear_listener_after_stop "$WEB_SERVICE" 3001'),
            2,
        )
        self.assertGreaterEqual(
            source.count('clear_listener_after_stop "$API_SERVICE" 8001'),
            2,
        )
        self.assertIn('mkdir -p "$RELEASE_DIR/apps/web/.next/cache"', source)
        self.assertIn('systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"', source)


if __name__ == "__main__":
    unittest.main()
