#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
APP_ENV="${APP_ENV:-/etc/hiddenoasis/staff-payroll.env}"
RUNTIME_BASE="${RUNTIME_BASE:-/opt/hiddenoasis/staff-payroll}"
RELEASES_DIR="$RUNTIME_BASE/releases"
CURRENT_LINK="$RUNTIME_BASE/current"
STATE_DIR="${STATE_DIR:-/var/lib/hiddenoasis/staff-payroll}"
TARGET_DB="$STATE_DIR/staff_payroll.sqlite"
TARGET_UPLOADS="$STATE_DIR/uploads"
PENDING_ENV="$STATE_DIR/runtime-env.pending"
SOURCE_DB="${SOURCE_DB:-$APP_ROOT/data/staff_payroll.sqlite}"
SOURCE_UPLOADS="${SOURCE_UPLOADS:-$APP_ROOT/data/staff_uploads}"
SERVICE_USER="${SERVICE_USER:-staff-payroll}"
SERVICE_GROUP="${SERVICE_GROUP:-staff-payroll}"
API_SERVICE="staff-payroll-api.service"
WEB_SERVICE="staff-payroll-web.service"
WORKER_SERVICE="hiddenoasis-staff-integration-worker.service"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/hidden-oasis-staff-payroll/cutover}"
READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-45}"
CUTOVER_STARTED_AT="$(date --iso-8601=seconds)"

fail() {
  echo "Fatal: $*" >&2
  return 1
}

listener_pid() {
  local port="$1"
  ss -ltnp "sport = :$port" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
    | head -n 1
}

clear_listener_after_stop() {
  local service="$1" port="$2"
  local main_pid listen_pid
  main_pid="$(systemctl show "$service" -p MainPID --value 2>/dev/null || true)"
  listen_pid="$(listener_pid "$port")"
  [[ -n "$listen_pid" ]] || return 0

  if [[ -n "$main_pid" && "$main_pid" != "0" && "$listen_pid" == "$main_pid" ]]; then
    echo "Waiting for stopped service $service PID $main_pid to release port $port..."
  else
    echo "Clearing stale listener PID $listen_pid from port $port before starting $service..."
  fi

  kill -TERM "$listen_pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$listen_pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$listen_pid" 2>/dev/null; then
    echo "Listener PID $listen_pid did not exit after SIGTERM; sending SIGKILL" >&2
    kill -KILL "$listen_pid" 2>/dev/null || true
  fi

  for _ in $(seq 1 10); do
    [[ -z "$(listener_pid "$port")" ]] && return 0
    sleep 1
  done
  fail "port $port remains occupied after stopping $service"
}

wait_service_active() {
  local service="$1"
  local deadline=$((SECONDS + READINESS_TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    if systemctl is-active --quiet "$service"; then
      echo "OK service active: $service"
      return 0
    fi
    if systemctl is-failed --quiet "$service"; then
      echo "Service entered failed state: $service" >&2
      return 1
    fi
    sleep 1
  done
  echo "Timed out waiting for active service: $service" >&2
  return 1
}

wait_listener_owner() {
  local service="$1" port="$2"
  local deadline=$((SECONDS + READINESS_TIMEOUT_SECONDS))
  local main_pid listen_pid
  while (( SECONDS < deadline )); do
    main_pid="$(systemctl show "$service" -p MainPID --value)"
    listen_pid="$(listener_pid "$port")"
    if [[ -n "$main_pid" && "$main_pid" != "0" && "$main_pid" == "$listen_pid" ]]; then
      echo "OK listener ownership: $service PID $main_pid -> 127.0.0.1:$port"
      return 0
    fi
    if systemctl is-failed --quiet "$service"; then
      echo "$service failed before owning port $port" >&2
      return 1
    fi
    sleep 1
  done
  main_pid="$(systemctl show "$service" -p MainPID --value)"
  listen_pid="$(listener_pid "$port")"
  echo "Timed out waiting for $service MainPID $main_pid to own port $port (listener ${listen_pid:-none})" >&2
  return 1
}

wait_http() {
  local label="$1" url="$2"
  local deadline=$((SECONDS + READINESS_TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "OK HTTP ready: $label"
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for HTTP readiness: $label ($url)" >&2
  return 1
}

[[ "$(id -u)" == "0" ]] || fail "cutover must run as root"
cd "$APP_ROOT"
[[ -z "$(git status --porcelain)" ]] || fail "working tree is dirty"
[[ -f "$APP_ENV" ]] || fail "missing live env: $APP_ENV"
[[ -f "$PENDING_ENV" ]] || fail "missing pending runtime env: $PENDING_ENV"
[[ -f "$SOURCE_DB" ]] || fail "missing source database: $SOURCE_DB"
id "$SERVICE_USER" >/dev/null 2>&1 || fail "missing service user: $SERVICE_USER"

SHA="$(git rev-parse HEAD)"
RELEASE_DIR="$RELEASES_DIR/$SHA"
[[ -d "$RELEASE_DIR" ]] || fail "runtime release is not staged: $RELEASE_DIR"
[[ -x "$RELEASE_DIR/.venv-api/bin/python" ]] || fail "runtime Python environment is missing"
[[ -f "$RELEASE_DIR/apps/web/.next/BUILD_ID" ]] || fail "runtime web build is missing"

# core.db retains a legacy DATA_DIR.mkdir(exist_ok=True) call even when the
# configured SQLite database lives in /var/lib. The immutable release must
# therefore contain an empty application data directory. It stays root-owned
# and non-writable by the service account.
mkdir -p "$RELEASE_DIR/data"
chown root:"$SERVICE_GROUP" "$RELEASE_DIR/data"
chmod 0750 "$RELEASE_DIR/data"

# Next may omit .next/cache on a clean production build. Create it explicitly
# so the service sandbox always has a concrete writable cache target.
mkdir -p "$RELEASE_DIR/apps/web/.next/cache"
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$RELEASE_DIR/apps/web/.next/cache"
chmod 0700 "$RELEASE_DIR/apps/web/.next/cache"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
CUTOVER_BACKUP="$BACKUP_ROOT/$TIMESTAMP"
install -d -m 0700 "$CUTOVER_BACKUP"
cp -a "$APP_ENV" "$CUTOVER_BACKUP/staff-payroll.env.before"
for unit in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
  if [[ -f "/etc/systemd/system/$unit" ]]; then
    cp -a "/etc/systemd/system/$unit" "$CUTOVER_BACKUP/$unit.before"
  fi
done

PREVIOUS_LINK=""
if [[ -L "$CURRENT_LINK" ]]; then
  PREVIOUS_LINK="$(readlink -f "$CURRENT_LINK" || true)"
fi

rollback() {
  local status="$1"
  local failed_command="$2"
  echo "Cutover failed while running: $failed_command" >&2
  echo "Cutover-window service diagnostics before rollback:" >&2
  for unit in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
    echo "--- $unit" >&2
    systemctl status "$unit" --no-pager -l >&2 || true
    journalctl -u "$unit" --since "$CUTOVER_STARTED_AT" --no-pager -o short-iso >&2 || true
  done
  echo "Restoring previous production configuration." >&2

  systemctl stop "$WORKER_SERVICE" || true
  systemctl stop "$WEB_SERVICE" || true
  systemctl stop "$API_SERVICE" || true
  clear_listener_after_stop "$WEB_SERVICE" 3001 || true
  clear_listener_after_stop "$API_SERVICE" 8001 || true

  cp -a "$CUTOVER_BACKUP/staff-payroll.env.before" "$APP_ENV" || true
  for unit in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
    if [[ -f "$CUTOVER_BACKUP/$unit.before" ]]; then
      cp -a "$CUTOVER_BACKUP/$unit.before" "/etc/systemd/system/$unit" || true
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
  exit "$status"
}
trap 'status=$?; failed_command=$BASH_COMMAND; rollback "$status" "$failed_command"' ERR

echo "Stopping write-producing services for final state synchronization..."
systemctl stop "$WORKER_SERVICE"
systemctl stop "$WEB_SERVICE"
systemctl stop "$API_SERVICE"
clear_listener_after_stop "$WEB_SERVICE" 3001
clear_listener_after_stop "$API_SERVICE" 8001

SOURCE_DB="$SOURCE_DB" TARGET_DB="$TARGET_DB" python3 - <<'PY'
import os
import sqlite3
from pathlib import Path
source = Path(os.environ["SOURCE_DB"]).resolve()
target = Path(os.environ["TARGET_DB"]).resolve()
target.parent.mkdir(parents=True, exist_ok=True)
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(target) + suffix)
    if candidate.exists():
        candidate.unlink()
s = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
t = sqlite3.connect(str(target))
try:
    s.backup(t)
    result = t.execute("PRAGMA integrity_check").fetchone()
    if not result or str(result[0]).lower() != "ok":
        raise SystemExit(f"final database copy failed integrity check: {result}")
finally:
    t.close()
    s.close()
PY
chown "$SERVICE_USER":"$SERVICE_GROUP" "$TARGET_DB"
chmod 0600 "$TARGET_DB"

if [[ -d "$SOURCE_UPLOADS" ]]; then
  SOURCE_UPLOADS="$SOURCE_UPLOADS" TARGET_UPLOADS="$TARGET_UPLOADS" python3 - <<'PY'
import os
import shutil
from pathlib import Path
source = Path(os.environ["SOURCE_UPLOADS"])
target = Path(os.environ["TARGET_UPLOADS"])
target.mkdir(parents=True, exist_ok=True)
for path in source.rglob("*"):
    rel = path.relative_to(source)
    dest = target / rel
    if path.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
    elif path.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
PY
  chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$TARGET_UPLOADS"
  chmod -R u+rwX,go-rwx "$TARGET_UPLOADS"
fi

APP_ENV="$APP_ENV" PENDING_ENV="$PENDING_ENV" python3 - <<'PY'
import os
from pathlib import Path
path = Path(os.environ["APP_ENV"])
pending = Path(os.environ["PENDING_ENV"])
updates = {}
for line in pending.read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        updates[key] = value
lines = path.read_text(encoding="utf-8").splitlines()
out = []
seen = set()
for line in lines:
    stripped = line.strip()
    key = stripped.split("=", 1)[0] if "=" in stripped else None
    if key in updates:
        if key not in seen:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        if out and out[-1] != "":
            out.append("")
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
chmod 0600 "$APP_ENV"

install -m 0644 deployment/staff-payroll-api.service "/etc/systemd/system/$API_SERVICE"
install -m 0644 deployment/staff-payroll-web.service "/etc/systemd/system/$WEB_SERVICE"
install -m 0644 deployment/hiddenoasis-staff-integration-worker.service "/etc/systemd/system/$WORKER_SERVICE"
systemctl daemon-reload
systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true

ln -sfn "$RELEASE_DIR" "$RUNTIME_BASE/.current.new"
mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"

systemctl restart "$API_SERVICE"
systemctl restart "$WEB_SERVICE"
systemctl restart "$WORKER_SERVICE"

wait_service_active "$API_SERVICE"
wait_service_active "$WEB_SERVICE"
wait_service_active "$WORKER_SERVICE"
[[ "$(systemctl show "$API_SERVICE" -p User --value)" == "$SERVICE_USER" ]] || fail "API is not running as $SERVICE_USER"
[[ "$(systemctl show "$WEB_SERVICE" -p User --value)" == "$SERVICE_USER" ]] || fail "web is not running as $SERVICE_USER"
[[ "$(systemctl show "$WORKER_SERVICE" -p User --value)" == "$SERVICE_USER" ]] || fail "worker is not running as $SERVICE_USER"
wait_listener_owner "$API_SERVICE" 8001
wait_listener_owner "$WEB_SERVICE" 3001
wait_http "API" "http://127.0.0.1:8001/health"
wait_http "web" "http://127.0.0.1:3001/login"

TARGET_DB="$TARGET_DB" "$RELEASE_DIR/.venv-api/bin/python" - <<'PY'
import os
import sqlite3
path = os.environ["TARGET_DB"]
conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
try:
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if not result or str(result[0]).lower() != "ok":
        raise SystemExit(f"runtime DB integrity failure: {result}")
finally:
    conn.close()
PY

trap - ERR
echo "Non-root runtime cutover completed successfully."
echo "Rollback material retained at: $CUTOVER_BACKUP"
