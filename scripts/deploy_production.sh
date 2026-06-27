#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
APP_ENV="${APP_ENV:-/etc/hidden-oasis-payroll/app.env}"
API_SERVICE="${API_SERVICE:-hidden-oasis-payroll-api}"
WEB_SERVICE="${WEB_SERVICE:-hidden-oasis-payroll-web}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8001/health}"
WEB_HEALTH_URL="${WEB_HEALTH_URL:-http://127.0.0.1:3001}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-/var/lib/hidden-oasis-payroll/deployed-sha}"

cd "$APP_ROOT"

CURRENT_COMMIT="$(git rev-parse HEAD)"
PREVIOUS_DEPLOYED_COMMIT=""
if [[ -f "$DEPLOY_STATE_FILE" ]]; then
  PREVIOUS_DEPLOYED_COMMIT="$(cat "$DEPLOY_STATE_FILE")"
fi

rollback() {
  local status=$?
  echo "Deployment failed with status $status."
  if [[ -n "$PREVIOUS_DEPLOYED_COMMIT" ]]; then
    echo "Rolling back to previous deployed SHA: $PREVIOUS_DEPLOYED_COMMIT"
    git reset --hard "$PREVIOUS_DEPLOYED_COMMIT"
    systemctl restart "$API_SERVICE"
    systemctl restart "$WEB_SERVICE"
    systemctl reload nginx || true
  else
    echo "No previous deployed SHA recorded; manual rollback required."
  fi
  exit "$status"
}
trap rollback ERR

echo "Deploying Hidden Oasis Staff Payroll"
echo "App root: $APP_ROOT"
echo "Current commit: $CURRENT_COMMIT"
if [[ -n "$PREVIOUS_DEPLOYED_COMMIT" ]]; then
  echo "Previous deployed commit: $PREVIOUS_DEPLOYED_COMMIT"
fi

if [[ ! -f "$APP_ENV" ]]; then
  echo "Fatal: env file not found at $APP_ENV. Refusing to deploy without production configuration."
  exit 1
fi
set -a
# shellcheck source=/dev/null
source "$APP_ENV"
set +a

echo "Creating database backup..."
python3 scripts/backup_database.py

if [[ -f scripts/backup_package.py ]]; then
  echo "Creating database + uploads backup package..."
  python3 scripts/backup_package.py
fi

echo "Compiling Python..."
python3 -m compileall api core scripts tests

if [[ -d tests ]]; then
  echo "Running Python tests..."
  python3 -m unittest discover -s tests
fi

echo "Running production preflight..."
if [[ -x .venv-api/bin/python ]]; then
  .venv-api/bin/python scripts/production_preflight.py
else
  python3 scripts/production_preflight.py
fi

echo "Building web app..."
cd apps/web
npm ci
rm -rf .next
npm run build

cd "$APP_ROOT"

echo "Restarting services..."
systemctl restart "$API_SERVICE"
systemctl restart "$WEB_SERVICE"
systemctl reload nginx

sleep 3

echo "Checking API health..."
curl -fsS "$API_HEALTH_URL"
echo

echo "Checking web health..."
curl -fsS "$WEB_HEALTH_URL" >/dev/null

mkdir -p "$(dirname "$DEPLOY_STATE_FILE")"
printf '%s\n' "$CURRENT_COMMIT" > "$DEPLOY_STATE_FILE"
trap - ERR

echo "Deployment completed successfully."
