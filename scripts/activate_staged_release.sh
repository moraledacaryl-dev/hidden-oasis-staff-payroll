#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
RUNTIME_BASE="${RUNTIME_BASE:-/opt/hiddenoasis/staff-payroll}"
CURRENT_LINK="$RUNTIME_BASE/current"
API_SERVICE="${API_SERVICE:-staff-payroll-api.service}"
WEB_SERVICE="${WEB_SERVICE:-staff-payroll-web.service}"
WORKER_SERVICE="${WORKER_SERVICE:-hiddenoasis-staff-integration-worker.service}"
LEGACY_API_SERVICE="${LEGACY_API_SERVICE:-hidden-oasis-payroll-api.service}"
LEGACY_WEB_SERVICE="${LEGACY_WEB_SERVICE:-hidden-oasis-payroll-web.service}"
WEB_UNIT_PATH="/etc/systemd/system/$WEB_SERVICE"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8001/health}"
WEB_HEALTH_URL="${WEB_HEALTH_URL:-http://127.0.0.1:3001/login}"
READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-45}"

cd "$APP_ROOT"
SHA="$(git rev-parse HEAD)"
RELEASE_DIR="$RUNTIME_BASE/releases/$SHA"
PREVIOUS_RELEASE="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
WEB_UNIT_BACKUP=""
ACTIVATED=0
WEB_RUNTIME_MASKED=0

listener_pid() {
  local port="$1"
  ss -ltnp "sport = :$port" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
    | head -n 1
}

kill_listener() {
  local port="$1" pid
  pid="$(listener_pid "$port")"
  [[ -n "$pid" ]] || return 0
  echo "Terminating stale listener PID $pid on port $port"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  kill -KILL "$pid" 2>/dev/null || true
}

wait_port_stably_free() {
  local port="$1" stable=0
  for _ in $(seq 1 30); do
    if [[ -z "$(listener_pid "$port")" ]]; then
      stable=$((stable + 1))
      if (( stable >= 5 )); then
        echo "Port $port remained free for 5 consecutive checks."
        return 0
      fi
    else
      stable=0
      kill_listener "$port"
    fi
    sleep 1
  done
  echo "Fatal: port $port could not be kept free" >&2
  return 1
}

wait_service_inactive() {
  local service="$1"
  for _ in $(seq 1 15); do
    if ! systemctl is-active --quiet "$service"; then
      return 0
    fi
    sleep 1
  done
  echo "Fatal: $service did not remain inactive during quiescence" >&2
  systemctl status "$service" --no-pager -l >&2 || true
  return 1
}

legacy_unit_exists() {
  local service="$1"
  [[ "$(systemctl show "$service" -p LoadState --value 2>/dev/null || true)" != "not-found" ]]
}

fence_legacy_runtime() {
  local service="$1" role="$2"
  legacy_unit_exists "$service" || return 0

  echo "Retiring deprecated $role unit: $service"
  # The pre-hardening root-owned units are independent supervisors. Killing a
  # child listener is insufficient because Restart= can immediately recreate
  # it. Disable them persistently, runtime-mask queued restarts, then kill the
  # complete cgroup and prove the unit is inactive before touching current.
  systemctl disable --now "$service" >/dev/null 2>&1 || true
  systemctl mask --runtime --now "$service" >/dev/null 2>&1 || true
  systemctl kill --kill-who=all --signal=SIGKILL "$service" >/dev/null 2>&1 || true
  systemctl reset-failed "$service" >/dev/null 2>&1 || true
  wait_service_inactive "$service"
}

fence_legacy_api_runtime() {
  fence_legacy_runtime "$LEGACY_API_SERVICE" "API"
}

fence_legacy_web_runtime() {
  fence_legacy_runtime "$LEGACY_WEB_SERVICE" "web"
}

mask_web_runtime() {
  # --now stops the loaded unit at the same boundary where the runtime mask is
  # installed, preventing an already queued Restart=on-failure job from racing
  # a separate stop-then-mask sequence.
  systemctl mask --runtime --now "$WEB_SERVICE" >/dev/null
  WEB_RUNTIME_MASKED=1
  systemctl daemon-reload >/dev/null
  systemctl reset-failed "$WEB_SERVICE" >/dev/null 2>&1 || true
  wait_service_inactive "$WEB_SERVICE"
}

unmask_web_runtime() {
  if [[ "$WEB_RUNTIME_MASKED" == "1" ]]; then
    systemctl unmask --runtime "$WEB_SERVICE" >/dev/null || true
    WEB_RUNTIME_MASKED=0
  fi
}

quiesce_old_runtime() {
  echo "Stopping old runtime before changing current release..."
  # Fence both deprecated root-owned supervisors first. Production evidence
  # found hidden-oasis-payroll-web.service owning 3001 and
  # hidden-oasis-payroll-api.service auto-restarting against 8001.
  fence_legacy_web_runtime
  fence_legacy_api_runtime
  # Fence canonical web next. The previous stop -> mask ordering allowed
  # RestartSec=3 to queue a new web process between those two operations.
  mask_web_runtime
  systemctl stop "$WORKER_SERVICE" || true
  systemctl stop "$API_SERVICE" || true
  systemctl kill --kill-who=all --signal=SIGKILL "$WEB_SERVICE" >/dev/null 2>&1 || true
  systemctl kill --kill-who=all --signal=SIGKILL "$API_SERVICE" >/dev/null 2>&1 || true
  systemctl reset-failed "$WEB_SERVICE" >/dev/null 2>&1 || true
  wait_service_inactive "$WEB_SERVICE"
  wait_service_inactive "$LEGACY_WEB_SERVICE" || true
  wait_service_inactive "$LEGACY_API_SERVICE" || true
  kill_listener 3001
  kill_listener 8001
  wait_port_stably_free 3001
  wait_service_inactive "$WEB_SERVICE"
  wait_service_inactive "$LEGACY_WEB_SERVICE" || true
  wait_port_stably_free 8001
  wait_service_inactive "$LEGACY_API_SERVICE" || true
}

runtime_ready() {
  local api_pid web_pid api_listener web_listener
  systemctl is-active --quiet "$API_SERVICE" || return 1
  systemctl is-active --quiet "$WEB_SERVICE" || return 1
  systemctl is-active --quiet "$WORKER_SERVICE" || return 1
  if legacy_unit_exists "$LEGACY_WEB_SERVICE" && systemctl is-active --quiet "$LEGACY_WEB_SERVICE"; then
    return 1
  fi
  if legacy_unit_exists "$LEGACY_API_SERVICE" && systemctl is-active --quiet "$LEGACY_API_SERVICE"; then
    return 1
  fi
  api_pid="$(systemctl show "$API_SERVICE" -p MainPID --value)"
  web_pid="$(systemctl show "$WEB_SERVICE" -p MainPID --value)"
  api_listener="$(listener_pid 8001)"
  web_listener="$(listener_pid 3001)"
  [[ -n "$api_pid" && "$api_pid" != "0" && "$api_pid" == "$api_listener" ]] || return 1
  [[ -n "$web_pid" && "$web_pid" != "0" && "$web_pid" == "$web_listener" ]] || return 1
  curl -fsS "$API_HEALTH_URL" >/dev/null 2>&1 || return 1
  curl -fsS "$WEB_HEALTH_URL" >/dev/null 2>&1 || return 1
  return 0
}

wait_runtime_ready() {
  for waited in $(seq 0 "$READINESS_TIMEOUT_SECONDS"); do
    if runtime_ready; then
      echo "Runtime readiness PASS after ${waited}s"
      return 0
    fi
    sleep 1
  done
  return 1
}

restore_preswitch_runtime() {
  echo "Pre-switch quiescence failed; restoring untouched current runtime." >&2
  unmask_web_runtime
  systemctl daemon-reload || true
  systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true
  systemctl start "$API_SERVICE" || true
  systemctl start "$WEB_SERVICE" || true
  systemctl start "$WORKER_SERVICE" || true
  if wait_runtime_ready; then
    echo "Pre-switch runtime readiness restored."
    return 0
  fi
  echo "ERROR: failed to restore runtime after pre-switch quiescence failure." >&2
  systemctl status "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" --no-pager -l >&2 || true
  ss -ltnp | grep -E ':8001|:3001' >&2 || true
  return 1
}

rollback() {
  local rc="${1:-1}"
  echo "Activation failed; restoring previous release: $PREVIOUS_RELEASE" >&2
  systemctl stop "$WORKER_SERVICE" "$WEB_SERVICE" "$API_SERVICE" >/dev/null 2>&1 || true
  systemctl kill --kill-who=all --signal=SIGKILL "$WEB_SERVICE" >/dev/null 2>&1 || true
  systemctl kill --kill-who=all --signal=SIGKILL "$API_SERVICE" >/dev/null 2>&1 || true
  fence_legacy_web_runtime || true
  fence_legacy_api_runtime || true
  kill_listener 3001 || true
  kill_listener 8001 || true
  wait_port_stably_free 3001 || true
  wait_port_stably_free 8001 || true
  if [[ -n "$PREVIOUS_RELEASE" ]]; then
    ln -sfn "$PREVIOUS_RELEASE" "$RUNTIME_BASE/.current.rollback"
    mv -Tf "$RUNTIME_BASE/.current.rollback" "$CURRENT_LINK"
  fi
  if [[ -n "$WEB_UNIT_BACKUP" && -f "$WEB_UNIT_BACKUP" ]]; then
    install -m 0644 "$WEB_UNIT_BACKUP" "$WEB_UNIT_PATH"
  fi
  unmask_web_runtime
  systemctl daemon-reload || true
  systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true
  systemctl start "$API_SERVICE" || true
  systemctl start "$WEB_SERVICE" || true
  systemctl start "$WORKER_SERVICE" || true

  if wait_runtime_ready; then
    echo "Rollback runtime readiness restored."
  else
    echo "ERROR: rollback failed to restore canonical runtime readiness." >&2
    systemctl status "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" --no-pager -l >&2 || true
    ss -ltnp | grep -E ':8001|:3001' >&2 || true
    journalctl -u "$API_SERVICE" --since '-3 minutes' --no-pager -n 80 >&2 || true
    journalctl -u "$WEB_SERVICE" --since '-3 minutes' --no-pager -n 80 >&2 || true
    [[ -n "$WEB_UNIT_BACKUP" ]] && rm -f "$WEB_UNIT_BACKUP" || true
    exit 1
  fi

  [[ -n "$WEB_UNIT_BACKUP" ]] && rm -f "$WEB_UNIT_BACKUP" || true
  exit "$rc"
}

[[ "$(id -u)" == "0" ]] || { echo "Fatal: must run as root" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Fatal: dirty worktree" >&2; exit 1; }
[[ -d "$RELEASE_DIR" ]] || { echo "Fatal: staged release missing: $RELEASE_DIR" >&2; exit 1; }
[[ -f "$RELEASE_DIR/apps/web/.next/standalone/server.js" ]] \
  || { echo "Fatal: standalone server missing from staged release" >&2; exit 1; }
[[ -f "$APP_ROOT/deployment/$WEB_SERVICE" ]] \
  || { echo "Fatal: canonical web unit missing" >&2; exit 1; }

if [[ -f "$WEB_UNIT_PATH" ]]; then
  WEB_UNIT_BACKUP="$(mktemp /run/staff-payroll-web.service.before.XXXXXX)"
  cp -a "$WEB_UNIT_PATH" "$WEB_UNIT_BACKUP"
fi

# Critical ordering invariant: the old runtime and every service capable of
# owning the Staff web/API ports must be stopped before current can move.
if ! quiesce_old_runtime; then
  restore_preswitch_runtime || true
  [[ -n "$WEB_UNIT_BACKUP" ]] && rm -f "$WEB_UNIT_BACKUP" || true
  exit 1
fi

mkdir -p "$RUNTIME_BASE"
ln -sfn "$RELEASE_DIR" "$RUNTIME_BASE/.current.new"
mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"
ACTIVATED=1

# Every failure after the current symlink moves must explicitly enter rollback.
# Do not rely on `set -e`: a failed systemctl/install command would otherwise
# terminate the script and strand production in a partially activated state.
if ! install -m 0644 "$APP_ROOT/deployment/$WEB_SERVICE" "$WEB_UNIT_PATH"; then
  rollback 1
fi
unmask_web_runtime
if ! systemctl daemon-reload; then
  rollback 1
fi
systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true

# Re-fence both deprecated supervisors immediately before starting canonical
# services, then prove both ports stable-free. This catches delayed restart jobs.
fence_legacy_web_runtime || rollback 1
fence_legacy_api_runtime || rollback 1
kill_listener 3001
kill_listener 8001
if ! wait_port_stably_free 3001; then
  rollback 1
fi
if ! wait_port_stably_free 8001; then
  rollback 1
fi

if ! systemctl start "$API_SERVICE"; then
  rollback 1
fi
if ! systemctl start "$WEB_SERVICE"; then
  rollback 1
fi
if ! systemctl start "$WORKER_SERVICE"; then
  rollback 1
fi

if ! wait_runtime_ready; then
  systemctl status "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" --no-pager -l >&2 || true
  ss -ltnp | grep -E ':8001|:3001' >&2 || true
  rollback 1
fi

WEB_EXEC="$(systemctl show "$WEB_SERVICE" -p ExecStart --value)"
[[ "$WEB_EXEC" == *".next/standalone/server.js"* ]] || rollback 1

if legacy_unit_exists "$LEGACY_WEB_SERVICE" && systemctl is-active --quiet "$LEGACY_WEB_SERVICE"; then
  echo "Fatal: deprecated web service is active after activation: $LEGACY_WEB_SERVICE" >&2
  rollback 1
fi
if legacy_unit_exists "$LEGACY_API_SERVICE" && systemctl is-active --quiet "$LEGACY_API_SERVICE"; then
  echo "Fatal: deprecated API service is active after activation: $LEGACY_API_SERVICE" >&2
  rollback 1
fi

printf '%s\n' "$SHA" > /var/lib/hiddenoasis/staff-payroll/deployed-sha
chown staff-payroll:staff-payroll /var/lib/hiddenoasis/staff-payroll/deployed-sha
chmod 0600 /var/lib/hiddenoasis/staff-payroll/deployed-sha

[[ -n "$WEB_UNIT_BACKUP" ]] && rm -f "$WEB_UNIT_BACKUP" || true
ACTIVATED=0

echo "Staged release activation completed successfully: $SHA"
