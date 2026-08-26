#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
APP_ENV="${APP_ENV:-/etc/hiddenoasis/staff-payroll.env}"
RUNTIME_BASE="${RUNTIME_BASE:-/opt/hiddenoasis/staff-payroll}"
CURRENT_LINK="$RUNTIME_BASE/current"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/hidden-oasis-staff-payroll/dropin-migration}"
API_SERVICE="staff-payroll-api.service"
WEB_SERVICE="staff-payroll-web.service"
WORKER_SERVICE="hiddenoasis-staff-integration-worker.service"

[[ "$(id -u)" == "0" ]] || { echo "Fatal: migration must run as root" >&2; exit 1; }
cd "$APP_ROOT"
[[ -z "$(git status --porcelain)" ]] || { echo "Fatal: working tree is dirty" >&2; exit 1; }
[[ -f "$APP_ENV" ]] || { echo "Fatal: missing live env: $APP_ENV" >&2; exit 1; }

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
  echo "Terminating listener PID $pid on port $port..."
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
}

wait_port_stably_free() {
  local port="$1"
  local stable=0
  for _ in $(seq 1 30); do
    if [[ -z "$(listener_pid "$port")" ]]; then
      stable=$((stable + 1))
      if (( stable >= 3 )); then
        echo "Port $port remained free for 3 consecutive checks."
        return 0
      fi
    else
      stable=0
      kill_listener "$port"
    fi
    sleep 1
  done
  echo "Fatal: port $port could not be kept free before migration" >&2
  return 1
}

quiesce_runtime() {
  echo "Quiescing current runtime and all service descendants..."
  systemctl stop "$WORKER_SERVICE" || true
  systemctl stop "$WEB_SERVICE" || true
  systemctl stop "$API_SERVICE" || true

  # Legacy Next/Uvicorn launchers have historically left descendants alive
  # after the unit MainPID exits. Kill any remaining unit cgroup members, then
  # independently clear the known loopback listeners.
  systemctl kill --kill-who=all --signal=SIGKILL "$WEB_SERVICE" >/dev/null 2>&1 || true
  systemctl kill --kill-who=all --signal=SIGKILL "$API_SERVICE" >/dev/null 2>&1 || true

  kill_listener 3001
  kill_listener 8001
  wait_port_stably_free 3001
  wait_port_stably_free 8001
}

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
MIGRATION_BACKUP="$BACKUP_ROOT/$TIMESTAMP"
install -d -m 0700 "$MIGRATION_BACKUP"

PREVIOUS_LINK=""
if [[ -L "$CURRENT_LINK" ]]; then
  PREVIOUS_LINK="$(readlink -f "$CURRENT_LINK" || true)"
fi

# Snapshot the complete pre-migration systemd/environment state. The nested
# cutover has its own rollback for failures during activation; this outer
# snapshot also protects failures in the post-cutover effective-unit checks.
cp -a "$APP_ENV" "$MIGRATION_BACKUP/staff-payroll.env.before"
for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
  unit_path="/etc/systemd/system/$service"
  if [[ -f "$unit_path" ]]; then
    cp -a "$unit_path" "$MIGRATION_BACKUP/$service.before"
  fi
  dropin_dir="$unit_path.d"
  if [[ -d "$dropin_dir" ]]; then
    cp -a "$dropin_dir" "$MIGRATION_BACKUP/$service.d"
  fi
done

restore_complete_pre_migration_state() {
  local status="$1"
  echo "Non-root migration failed; restoring complete pre-migration state." >&2

  quiesce_runtime || true

  cp -a "$MIGRATION_BACKUP/staff-payroll.env.before" "$APP_ENV" || true
  chmod 0600 "$APP_ENV" || true

  for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
    unit_path="/etc/systemd/system/$service"
    if [[ -f "$MIGRATION_BACKUP/$service.before" ]]; then
      cp -a "$MIGRATION_BACKUP/$service.before" "$unit_path" || true
    fi

    dropin_dir="$unit_path.d"
    rm -rf "$dropin_dir"
    if [[ -d "$MIGRATION_BACKUP/$service.d" ]]; then
      cp -a "$MIGRATION_BACKUP/$service.d" "$dropin_dir" || true
    fi
  done

  if [[ -n "$PREVIOUS_LINK" ]]; then
    ln -sfn "$PREVIOUS_LINK" "$RUNTIME_BASE/.current.rollback" || true
    mv -Tf "$RUNTIME_BASE/.current.rollback" "$CURRENT_LINK" || true
  else
    rm -f "$CURRENT_LINK" || true
  fi

  systemctl daemon-reload || true
  systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true
  systemctl restart "$API_SERVICE" || true
  systemctl restart "$WEB_SERVICE" || true
  systemctl restart "$WORKER_SERVICE" || true

  echo "Complete rollback material restored from: $MIGRATION_BACKUP" >&2
  exit "$status"
}

trap 'status=$?; restore_complete_pre_migration_state "$status"' ERR

echo "Backing up legacy systemd drop-ins..."
for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
  dropin_dir="/etc/systemd/system/$service.d"
  if [[ -d "$dropin_dir" ]]; then
    echo "Saved: $dropin_dir"
  else
    echo "No drop-ins: $dropin_dir"
  fi
done

# Stop the legacy runtime before deleting its effective drop-ins. This also
# prevents a detached Next child from racing the non-root web service for 3001.
quiesce_runtime

echo "Removing legacy systemd drop-ins before non-root cutover..."
for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
  rm -rf "/etc/systemd/system/$service.d"
done
systemctl daemon-reload

for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
  dropins="$(systemctl show "$service" -p DropInPaths --value)"
  [[ -z "$dropins" ]] || {
    echo "Fatal: unexpected effective drop-ins remain for $service: $dropins" >&2
    exit 1
  }
done

echo "Legacy drop-ins removed from effective unit configuration."

echo "Running controlled non-root cutover..."
bash scripts/cutover_nonroot_runtime.sh

# The controlled cutover has succeeded. Verify the effective configuration,
# not merely the checked-in base unit files.
for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
  user="$(systemctl show "$service" -p User --value)"
  working_dir="$(systemctl show "$service" -p WorkingDirectory --value)"
  exec_start="$(systemctl show "$service" -p ExecStart --value)"
  dropins="$(systemctl show "$service" -p DropInPaths --value)"

  [[ "$user" == "staff-payroll" ]] || {
    echo "Fatal: $service effective User is $user" >&2
    exit 1
  }
  [[ "$working_dir" == /opt/hiddenoasis/staff-payroll/current* ]] || {
    echo "Fatal: $service effective WorkingDirectory is $working_dir" >&2
    exit 1
  }
  [[ "$exec_start" == *"/opt/hiddenoasis/staff-payroll/current"* ]] || {
    echo "Fatal: $service effective ExecStart does not use current runtime: $exec_start" >&2
    exit 1
  }
  [[ -z "$dropins" ]] || {
    echo "Fatal: $service still has effective drop-ins: $dropins" >&2
    exit 1
  }
done

trap - ERR
echo "Non-root systemd migration completed successfully."
echo "Complete rollback material retained at: $MIGRATION_BACKUP"
