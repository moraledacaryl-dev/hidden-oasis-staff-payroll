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

cd "$APP_ROOT"
CURRENT_COMMIT="$(git rev-parse HEAD)"
RELEASE_DIR="$RELEASES_DIR/$CURRENT_COMMIT"
PREVIOUS_RELEASE=""
ACTIVATED=0

fail() {
  echo "Fatal: $*" >&2
  exit 1
}

listener_pid() {
  local port="$1"
  ss -ltnp "sport = :$port" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
    | head -n 1
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

rollback_runtime() {
  local status=$?
  if [[ "$ACTIVATED" == "1" && -n "$PREVIOUS_RELEASE" ]]; then
    echo "Deployment failed; restoring previous runtime release: $PREVIOUS_RELEASE" >&2
    ln -sfn "$PREVIOUS_RELEASE" "$RUNTIME_BASE/.current.rollback"
    mv -Tf "$RUNTIME_BASE/.current.rollback" "$CURRENT_LINK"
    systemctl restart "$API_SERVICE" || true
    systemctl restart "$WEB_SERVICE" || true
    systemctl restart "$WORKER_SERVICE" || true
  fi
  exit "$status"
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
# shellcheck source=/dev/null
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

  # core.db still calls DATA_DIR.mkdir(exist_ok=True) even when the configured
  # SQLite path is external. Keep an empty application data directory in each
  # immutable release so that legacy compatibility check succeeds without
  # granting the service write access to application code.
  mkdir -p "$RELEASE_DIR/data"

  python3 -m venv "$RELEASE_DIR/.venv-api"
  "$RELEASE_DIR/.venv-api/bin/python" -m pip install --upgrade pip
  "$RELEASE_DIR/.venv-api/bin/pip" install -r "$RELEASE_DIR/requirements-api.txt"
  "$RELEASE_DIR/.venv-api/bin/pip" check

  cd "$RELEASE_DIR/apps/web"
  npm ci
  npm run build
  cd "$APP_ROOT"

  chown -R root:"$SERVICE_GROUP" "$RELEASE_DIR"
  chmod -R o-rwx "$RELEASE_DIR"
  chmod 0750 "$RELEASE_DIR/data"
  if [[ -d "$RELEASE_DIR/apps/web/.next/cache" ]]; then
    chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$RELEASE_DIR/apps/web/.next/cache"
    chmod -R u+rwX,g-rwx,o-rwx "$RELEASE_DIR/apps/web/.next/cache"
  fi
fi

mkdir -p "$RUNTIME_BASE"
ln -sfn "$RELEASE_DIR" "$RUNTIME_BASE/.current.new"
mv -Tf "$RUNTIME_BASE/.current.new" "$CURRENT_LINK"
ACTIVATED=1

echo "Restarting canonical services on staged release..."
systemctl restart "$API_SERVICE"
systemctl restart "$WEB_SERVICE"
systemctl restart "$WORKER_SERVICE"
sleep 3

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
