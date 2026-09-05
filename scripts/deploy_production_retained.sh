#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"

cd "$APP_ROOT"

echo "Running canonical production deployment..."
bash "$APP_ROOT/scripts/deploy_production.sh"

echo "Applying runtime release retention after successful deployment..."
if ! bash "$APP_ROOT/scripts/prune_runtime_releases.sh"; then
  echo "WARNING: deployment succeeded, but runtime release retention cleanup failed." >&2
fi

echo "Deployment and release retention workflow complete."
