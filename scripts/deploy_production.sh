#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
APP_ENV="${APP_ENV:-/etc/hiddenoasis/staff-payroll.env}"
API_SERVICE="${API_SERVICE:-staff-payroll-api.service}"
WEB_SERVICE="${WEB_SERVICE:-staff-payroll-web.service}"
WORKER_SERVICE="${WORKER_SERVICE:-hiddenoasis-staff-integration-worker.service}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8001/health}"
WEB_HEALTH_URL="${WEB_HEALTH_URL:-http://127.0.0.1:3001/login}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-/var/lib/hiddenoasis/staff-payroll/deployed-sha}"
API_VENV="${API_VENV:-$APP_ROOT/.venv-api}"
API_PYTHON="$API_VENV/bin/python"
API_PIP="$API_VENV/bin/pip"

cd "$APP_ROOT"
CURRENT_COMMIT="$(git rev-parse HEAD)"

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

echo "Deploying Hidden Oasis Staff Payroll"
echo "App root: $APP_ROOT"
echo "Current commit: $CURRENT_COMMIT"

[[ -z "$(git status --porcelain)" ]] \
  || fail "working tree is dirty; refusing production deployment"
[[ -f "$APP_ENV" ]] \
  || fail "env file not found at $APP_ENV"

set -a
# shellcheck source=/dev/null
source "$APP_ENV"
set +a

if [[ ! -x "$API_PYTHON" ]]; then
  echo "Creating API virtual environment..."
  python3 -m venv "$API_VENV"
fi

echo "Installing API dependencies..."
"$API_PYTHON" -m pip install --upgrade pip
"$API_PIP" install -r requirements-api.txt
"$API_PIP" check

echo "Creating database backup..."
"$API_PYTHON" scripts/backup_database.py

if [[ -f scripts/backup_package.py ]]; then
  echo "Creating database + uploads backup package..."
  "$API_PYTHON" scripts/backup_package.py
fi

echo "Compiling Python..."
"$API_PYTHON" -m compileall api core scripts tests

echo "Running Python tests..."
env \
  -u STAFF_PAYROLL_API_KEY \
  -u STAFF_PAYROLL_SESSION_SECRET \
  -u STAFF_PAYROLL_MFA_KEY \
  STAFF_PAYROLL_ENV=test \
  "$API_PYTHON" -W error::UserWarning -m unittest discover -v

echo "Running production preflight..."
"$API_PYTHON" scripts/production_preflight.py

echo "Running Python dependency audit when available..."
if "$API_PYTHON" -m pip_audit --version >/dev/null 2>&1; then
  "$API_PYTHON" -m pip_audit
fi

echo "Installing and validating web dependencies..."
cd apps/web
npm ci
npm audit --omit=dev --audit-level=high
npm audit --audit-level=high
npm run lint
npm run typecheck
rm -rf .next
npm run build
cd "$APP_ROOT"

echo "Restarting canonical services..."
systemctl restart "$API_SERVICE"
systemctl restart "$WEB_SERVICE"
systemctl restart "$WORKER_SERVICE"

sleep 3

verify_service_active "$API_SERVICE"
verify_service_active "$WEB_SERVICE"
verify_service_active "$WORKER_SERVICE"
verify_listener_owner "$API_SERVICE" 8001
verify_listener_owner "$WEB_SERVICE" 3001

echo "Checking API health..."
curl -fsS "$API_HEALTH_URL"
echo

echo "Checking web health..."
curl -fsS "$WEB_HEALTH_URL" >/dev/null

echo "Checking fresh worker warnings..."
if journalctl -u "$WORKER_SERVICE" --since '-2 minutes' -p warning --no-pager \
  | grep -qv '^-- No entries --$'; then
  echo "Warning: recent worker warning-level journal entries detected." >&2
  journalctl -u "$WORKER_SERVICE" --since '-2 minutes' -p warning --no-pager >&2
  exit 1
fi

mkdir -p "$(dirname "$DEPLOY_STATE_FILE")"
printf '%s\n' "$CURRENT_COMMIT" > "$DEPLOY_STATE_FILE"
chmod 600 "$DEPLOY_STATE_FILE"

echo "Deployment completed successfully."
