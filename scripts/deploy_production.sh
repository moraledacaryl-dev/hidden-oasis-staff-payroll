#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
APP_ENV="${APP_ENV:-/etc/hiddenoasis/staff-payroll.env}"
API_SERVICE="${API_SERVICE:-staff-payroll-api.service}"
WEB_SERVICE="${WEB_SERVICE:-staff-payroll-web.service}"
WORKER_SERVICE="${WORKER_SERVICE:-hiddenoasis-staff-integration-worker.service}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8001/health}"
WEB_HEALTH_URL="${WEB_HEALTH_URL:-http://127.0.0.1:3001/login}"
RUNTIME_BASE="${RUNTIME_BASE:-/opt/hiddenoasis/staff-payroll}"
RELEASES_DIR="$RUNTIME_BASE/releases"
CURRENT_LINK="$RUNTIME_BASE/current"
SERVICE_USER="${SERVICE_USER:-staff-payroll}"
SERVICE_GROUP="${SERVICE_GROUP:-staff-payroll}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-/var/lib/hiddenoasis/staff-payroll/deployed-sha}"
SOURCE_VENV="${SOURCE_VENV:-$APP_ROOT/.venv-api}"
SOURCE_PYTHON="$SOURCE_VENV/bin/python"
SOURCE_PIP="$SOURCE_VENV/bin/pip"
READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-45}"

cd "$APP_ROOT"
CURRENT_COMMIT="$(git rev-parse HEAD)"
RELEASE_DIR="$RELEASES_DIR/$CURRENT_COMMIT"
PREVIOUS_RELEASE=""
ACTIVATED=0

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
  echo "Fatal: port $port could not be kept free during runtime transition" >&2
  return 1
}

quiesce_runtime() {
  echo "Quiescing runtime and all service descendants..."
  systemctl stop "$WORKER_SERVICE" || true
  systemctl stop "$WEB_SERVICE" || true
  systemctl stop "$API_SERVICE" || true

  # Next/Uvicorn launchers can leave descendants alive after MainPID exits.
  # Kill all remaining cgroup members, independently clear known listeners,
  # then require the ports to remain free before any new service is started.
  systemctl kill --kill-who=all --signal=SIGKILL "$WEB_SERVICE" >/dev/null 2>&1 || true
  systemctl kill --kill-who=all --signal=SIGKILL "$API_SERVICE" >/dev/null 2>&1 || true

  kill_listener 3001
  kill_listener 8001
  wait_port_stably_free 3001
  wait_port_stably_free 8001
}

rollback_runtime() {
  local status="${1:-$?}"
  if [[ "$ACTIVATED" == "1" && -n "$PREVIOUS_RELEASE" ]]; then
    echo "Deployment failed; restoring previous runtime release: $PREVIOUS_RELEASE" >&2
    # Prevent a secondary failure during rollback from recursively entering
    # rollback again. Best-effort quiescence is followed by restoring the
    # prior immutable pointer and canonical services.
    ACTIVATED=0
    quiesce_runtime || true
    ln -sfn "$PREVIOUS_RELEASE" "$RUNTIME_BASE/.current.rollback"
    mv -Tf "$RUNTIME_BASE/.current.rollback" "$CURRENT_LINK"
    systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true
    systemctl start "$API_SERVICE" || true
    systemctl start "$WEB_SERVICE" || true
    systemctl start "$WORKER_SERVICE" || true
  fi
  exit "$status"
}

fail() {
  echo "Fatal: $*" >&2
  if [[ "$ACTIVATED" == "1" && -n "$PREVIOUS_RELEASE" ]]; then
    rollback_runtime 1
  fi
  exit 1
}

verify_listener_owner() {
  local service="$1"
  local port="$2"
  local main_pid listen_pid
  main_pid="$(systemctl show "$service" -p MainPID --value)"
  listen_pid="$(listener_pid "$port")"
  [[ -n "$main_pid" && "$main_pid" != "0" ]] \
    || fail "$service has no live MainPID"
  [[ -n "$listen_pid" ]] \
    || fail "nothing is listening on 127.0.0.1:$port"
  [[ "$main_pid" == "$listen_pid" ]] \
    || fail "$service MainPID $main_pid does not own port $port (listener PID $listen_pid)"
  echo "OK listener ownership: $service PID $main_pid -> 127.0.0.1:$port"
}

verify_service_active() {
  local service="$1"
  systemctl is-active --quiet "$service" \
    || fail "$service is not active"
  echo "OK service active: $service"
}

runtime_ready() {
  local api_pid web_pid api_listener web_listener
  systemctl is-active --quiet "$API_SERVICE" || return 1
  systemctl is-active --quiet "$WEB_SERVICE" || return 1
  systemctl is-active --quiet "$WORKER_SERVICE" || return 1

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
  local waited=0
  while (( waited < READINESS_TIMEOUT_SECONDS )); do
    if runtime_ready; then
      echo "OK runtime readiness established after ${waited}s"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  echo "Runtime readiness failed after ${READINESS_TIMEOUT_SECONDS}s; diagnostics:" >&2
  for unit in "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE"; do
    echo "--- $unit" >&2
    systemctl status "$unit" --no-pager -l >&2 || true
    journalctl -u "$unit" --since '-3 minutes' --no-pager -n 80 >&2 || true
  done
  ss -ltnp | grep -E ':8001|:3001' >&2 || true
  fail "runtime readiness timeout"
}

trap rollback_runtime ERR

echo "Deploying Hidden Oasis Staff Payroll"
echo "Source checkout: $APP_ROOT"
echo "Runtime base: $RUNTIME_BASE"
echo "Current commit: $CURRENT_COMMIT"

[[ "$(id -u)" == "0" ]] || fail "deployment must run as root"
id "$SERVICE_USER" >/dev/null 2>&1 || fail "service user $SERVICE_USER does not exist; run scripts/prepare_nonroot_runtime.sh first"
getent group "$SERVICE_GROUP" >/dev/null 2>&1 || fail "service group $SERVICE_GROUP does not exist"
[[ -z "$(git status --porcelain)" ]] || fail "working tree is dirty; refusing production deployment"
[[ -f "$APP_ENV" ]] || fail "env file not found at $APP_ENV"

set -a
source "$APP_ENV"
set +a

[[ "${STAFF_PAYROLL_DB_PATH:-}" == /var/lib/hiddenoasis/staff-payroll/* ]] \
  || fail "STAFF_PAYROLL_DB_PATH must use /var/lib/hiddenoasis/staff-payroll before non-root deployment"
[[ "${STAFF_UPLOAD_DIR:-}" == /var/lib/hiddenoasis/staff-payroll/* ]] \
  || fail "STAFF_UPLOAD_DIR must use /var/lib/hiddenoasis/staff-payroll before non-root deployment"
[[ "${STAFF_PAYROLL_BACKUP_DIR:-}" == /var/backups/hidden-oasis-staff-payroll/runtime* ]] \
  || fail "STAFF_PAYROLL_BACKUP_DIR must use /var/backups/hidden-oasis-staff-payroll/runtime before non-root deployment"

if [[ ! -x "$SOURCE_PYTHON" ]]; then
  echo "Creating source validation virtual environment..."
  python3 -m venv "$SOURCE_VENV"
fi

echo "Installing source API dependencies..."
"$SOURCE_PYTHON" -m pip install --upgrade pip
"$SOURCE_PIP" install -r requirements-api.txt
"$SOURCE_PIP" check

echo "Creating pre-deploy database backup..."
"$SOURCE_PYTHON" scripts/backup_database.py
if [[ -f scripts/backup_package.py ]]; then
  "$SOURCE_PYTHON" scripts/backup_package.py
fi

echo "Running source validation..."
"$SOURCE_PYTHON" -m compileall -q api core scripts tests
env \
  -u STAFF_PAYROLL_API_KEY \
  -u STAFF_PAYROLL_SESSION_SECRET \
  -u STAFF_PAYROLL_MFA_KEY \
  STAFF_PAYROLL_ENV=test \
  "$SOURCE_PYTHON" -W error::UserWarning -m unittest discover -v
"$SOURCE_PYTHON" scripts/production_preflight.py
if "$SOURCE_PYTHON" -m pip_audit --version >/dev/null 2>&1; then
  "$SOURCE_PYTHON" -m pip_audit
fi

cd apps/web
npm ci
npm audit --omit=dev --audit-level=high
npm audit --audit-level=high
npm run lint
npm run typecheck
rm -rf .next
npm run build
cd "$APP_ROOT"

if [[ -L "$CURRENT_LINK" ]]; then
  PREVIOUS_RELEASE="$(readlink -f "$CURRENT_LINK" || true)"
fi

if [[ ! -d "$RELEASE_DIR" ]]; then
  echo "Staging immutable runtime release: $RELEASE_DIR"
  mkdir -p "$RELEASE_DIR"
  tar \
    --exclude='./.git' \
    --exclude='./.venv-api' \
    --exclude='./data' \
    --exclude='./apps/web/node_modules' \
    --exclude='./apps/web/.next' \
    -cf - . | tar -xf - -C "$RELEASE_DIR"

  mkdir -p "$RELEASE_DIR/data"

  python3 -m venv "$RELEASE_DIR/.venv-api"
  "$RELEASE_DIR/.venv-api/bin/python" -m pip install --upgrade pip
  "$RELEASE_DIR/.venv-api/bin/pip" install -r "$RELEASE_DIR/requirements-api.txt"
  "$RELEASE_DIR/.venv-api/bin/pip" check

  cd "$RELEASE_DIR/apps/web"
  npm ci
  npm run build
  mkdir -p .next/cache
  cd "$APP_ROOT"

  chown -R root:"$SERVICE_GROUP" "$RELEASE_DIR"
  chmod -R o-rwx "$RELEASE_DIR"
  chmod 0750 "$RELEASE_DIR/data"
  chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$RELEASE_DIR/apps/web/.next/cache"
  chmod 0700 "$RELEASE_DIR/apps/web/.next/cache"
fi

mkdir -p "$RUNTIME_BASE"
ln -sfn "$RELEASE_DIR" "$RUNTIME_BASE/.current.new"
mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"
ACTIVATED=1

echo "Restarting canonical services on staged release..."
quiesce_runtime
systemctl reset-failed "$API_SERVICE" "$WEB_SERVICE" "$WORKER_SERVICE" || true
systemctl start "$API_SERVICE"
systemctl start "$WEB_SERVICE"
systemctl start "$WORKER_SERVICE"
wait_runtime_ready

verify_service_active "$API_SERVICE"
verify_service_active "$WEB_SERVICE"
verify_service_active "$WORKER_SERVICE"
verify_listener_owner "$API_SERVICE" 8001
verify_listener_owner "$WEB_SERVICE" 3001

[[ "$(systemctl show "$API_SERVICE" -p User --value)" == "$SERVICE_USER" ]] \
  || fail "$API_SERVICE is not running as $SERVICE_USER"
[[ "$(systemctl show "$WEB_SERVICE" -p User --value)" == "$SERVICE_USER" ]] \
  || fail "$WEB_SERVICE is not running as $SERVICE_USER"
[[ "$(systemctl show "$WORKER_SERVICE" -p User --value)" == "$SERVICE_USER" ]] \
  || fail "$WORKER_SERVICE is not running as $SERVICE_USER"

echo "Checking API health..."
curl -fsS "$API_HEALTH_URL"
echo

echo "Checking web health..."
curl -fsS "$WEB_HEALTH_URL" >/dev/null

echo "Checking fresh worker warnings..."
if journalctl -u "$WORKER_SERVICE" --since '-2 minutes' -p warning --no-pager \
  | grep -qv '^-- No entries --$'; then
  journalctl -u "$WORKER_SERVICE" --since '-2 minutes' -p warning --no-pager >&2
  fail "recent worker warning-level journal entries detected"
fi

mkdir -p "$(dirname "$DEPLOY_STATE_FILE")"
printf '%s\n' "$CURRENT_COMMIT" > "$DEPLOY_STATE_FILE"
chown "$SERVICE_USER":"$SERVICE_GROUP" "$DEPLOY_STATE_FILE"
chmod 600 "$DEPLOY_STATE_FILE"
ACTIVATED=0
trap - ERR

echo "Deployment completed successfully."
