#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${STAFF_PAYROLL_TEST_PYTHON:-/root/repos/hidden-oasis-staff-payroll/.venv-api/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python environment not found or not executable: $PYTHON_BIN" >&2
  echo "Set STAFF_PAYROLL_TEST_PYTHON to the correct virtualenv Python path." >&2
  exit 1
fi

cd "$ROOT_DIR"

# Production values must never leak into unit tests. The application treats an
# unset API key as local/test mode, while the tests use disposable databases.
unset STAFF_PAYROLL_ENV
unset STAFF_PAYROLL_API_KEY
unset STAFF_PAYROLL_SESSION_SECRET
unset STAFF_PAYROLL_DB_PATH
unset STAFF_PAYROLL_CORS_ORIGINS
unset STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED
unset STAFF_PAYROLL_ACCOUNTING_SYNC_URL
unset STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN
unset STAFF_PAYROLL_OPERATIONS_SYNC_URL
unset STAFF_PAYROLL_OPERATIONS_SYNC_TOKEN
unset STAFF_PAYROLL_POS_SYNC_URL
unset STAFF_PAYROLL_POS_SYNC_TOKEN
unset STAFF_PAYROLL_INVENTORY_SYNC_URL
unset STAFF_PAYROLL_INVENTORY_SYNC_TOKEN

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/hidden-oasis-pycache}"

"$PYTHON_BIN" -m compileall -q api core scripts tests
"$PYTHON_BIN" -m unittest discover -v
