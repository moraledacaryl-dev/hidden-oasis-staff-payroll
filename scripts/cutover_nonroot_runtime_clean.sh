#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/hidden-oasis-staff-payroll/dropin-migration}"
API_SERVICE="staff-payroll-api.service"
WEB_SERVICE="staff-payroll-web.service"
WORKER_SERVICE="hiddenoasis-staff-integration-worker.service"

[[ "$(id -u)" == "0" ]] || { echo "Fatal: migration must run as root" >&2; exit 1; }
cd "$APP_ROOT"
[[ -z "$(git status --porcelain)" ]] || { echo "Fatal: working tree is dirty" >&2; exit 1; }

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DROPIN_BACKUP="$BACKUP_ROOT/$TIMESTAMP"
install -d -m 0700 "$DROPIN_BACKUP"

restore_dropins_and_root_runtime() {
  local status="$1"
  echo "Non-root migration failed; restoring legacy systemd drop-ins." >&2

  for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
    systemctl stop "$service" >/dev/null 2>&1 || true
  done

  for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
    dropin_dir="/etc/systemd/system/$service.d"
    rm -rf "$dropin_dir"
    if [[ -d "$DROPIN_BACKUP/$service.d" ]]; then
      cp -a "$DROPIN_BACKUP/$service.d" "$dropin_dir"
    fi
  done

  systemctl daemon-reload || true
  systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true
  systemctl restart "$API_SERVICE" || true
  systemctl restart "$WEB_SERVICE" || true
  systemctl restart "$WORKER_SERVICE" || true

  echo "Legacy drop-ins restored from: $DROPIN_BACKUP" >&2
  exit "$status"
}

trap 'status=$?; restore_dropins_and_root_runtime "$status"' ERR

echo "Backing up legacy systemd drop-ins..."
for service in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
  dropin_dir="/etc/systemd/system/$service.d"
  if [[ -d "$dropin_dir" ]]; then
    cp -a "$dropin_dir" "$DROPIN_BACKUP/$service.d"
    echo "Saved: $dropin_dir"
  else
    echo "No drop-ins: $dropin_dir"
  fi
done

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
echo "Legacy drop-in rollback material retained at: $DROPIN_BACKUP"
