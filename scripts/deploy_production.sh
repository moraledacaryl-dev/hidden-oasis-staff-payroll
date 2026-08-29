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
  local service="$1" port="$2" main_pid listen_pid
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

echo "Deploying Hidden Oasis Staff Payroll"
echo "Source checkout: $APP_ROOT"
echo "Runtime base: $RUNTIME_BASE"
echo "Current commit: $CURRENT_COMMIT"

[[ "$(id -u)" == "0" ]] || fail "deployment must run as root"
id "$SERVICE_USER" >/dev/null 2>&1 \
  || fail "service user $SERVICE_USER does not exist; run scripts/prepare_nonroot_runtime.sh first"
getent group "$SERVICE_GROUP" >/dev/null 2>&1 \
  || fail "service group $SERVICE_GROUP does not exist"
[[ -z "$(git status --porcelain)" ]] \
  || fail "working tree is dirty; refusing production deployment"
[[ -f "$APP_ENV" ]] || fail "env file not found at $APP_ENV"
[[ -x "$APP_ROOT/scripts/activate_staged_release.sh" || -f "$APP_ROOT/scripts/activate_staged_release.sh" ]] \
  || fail "safe staged activator is missing"
[[ -f "$APP_ROOT/deployment/$WEB_SERVICE" ]] \
  || fail "canonical web unit missing from deployment/$WEB_SERVICE"

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
test -f .next/standalone/server.js
mkdir -p .next/standalone/.next
rm -rf .next/standalone/.next/static .next/standalone/public
cp -a .next/static .next/standalone/.next/static
if [[ -d public ]]; then
  cp -a public .next/standalone/public
fi
cd "$APP_ROOT"

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
  test -f .next/standalone/server.js
  mkdir -p .next/standalone/.next .next/cache
  rm -rf .next/standalone/.next/static .next/standalone/public
  cp -a .next/static .next/standalone/.next/static
  if [[ -d public ]]; then
    cp -a public .next/standalone/public
  fi
  cd "$APP_ROOT"

  chown -R root:"$SERVICE_GROUP" "$RELEASE_DIR"
  chmod -R o-rwx "$RELEASE_DIR"
  chmod 0750 "$RELEASE_DIR/data"
  chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$RELEASE_DIR/apps/web/.next/cache"
  chmod 0700 "$RELEASE_DIR/apps/web/.next/cache"
fi

[[ -f "$RELEASE_DIR/apps/web/.next/standalone/server.js" ]] \
  || fail "staged standalone Next server is missing"

# The staged activator is the single authority for production cutover. It owns
# runtime quiescence, web restart fencing, current-symlink mutation, systemd
# unit installation, listener ownership checks, rollback, and deployed-sha.
echo "Activating staged release through canonical safe activator..."
bash "$APP_ROOT/scripts/activate_staged_release.sh"

echo "Running post-activation acceptance checks..."
[[ "$(readlink -f "$CURRENT_LINK")" == "$RELEASE_DIR" ]] \
  || fail "current release does not match $CURRENT_COMMIT"
[[ -f "$DEPLOY_STATE_FILE" ]] \
  || fail "deployment state marker is missing"
[[ "$(cat "$DEPLOY_STATE_FILE")" == "$CURRENT_COMMIT" ]] \
  || fail "deployment state marker does not match $CURRENT_COMMIT"

systemctl is-active --quiet "$API_SERVICE" || fail "$API_SERVICE is not active"
systemctl is-active --quiet "$WEB_SERVICE" || fail "$WEB_SERVICE is not active"
systemctl is-active --quiet "$WORKER_SERVICE" || fail "$WORKER_SERVICE is not active"

verify_listener_owner "$API_SERVICE" 8001
verify_listener_owner "$WEB_SERVICE" 3001

[[ "$(systemctl show "$API_SERVICE" -p User --value)" == "$SERVICE_USER" ]] \
  || fail "$API_SERVICE is not running as $SERVICE_USER"
[[ "$(systemctl show "$WEB_SERVICE" -p User --value)" == "$SERVICE_USER" ]] \
  || fail "$WEB_SERVICE is not running as $SERVICE_USER"
[[ "$(systemctl show "$WORKER_SERVICE" -p User --value)" == "$SERVICE_USER" ]] \
  || fail "$WORKER_SERVICE is not running as $SERVICE_USER"
[[ "$(systemctl show "$WEB_SERVICE" -p ExecStart --value)" == *".next/standalone/server.js"* ]] \
  || fail "$WEB_SERVICE is not using the standalone server"

curl -fsS "$API_HEALTH_URL" >/dev/null
curl -fsS "$WEB_HEALTH_URL" >/dev/null

if journalctl -u "$WORKER_SERVICE" --since '-2 minutes' -p warning --no-pager \
  | grep -qv '^-- No entries --$'; then
  journalctl -u "$WORKER_SERVICE" --since '-2 minutes' -p warning --no-pager >&2
  fail "recent worker warning-level journal entries detected"
fi

echo "Deployment completed successfully through canonical staged activator."
