#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/repos/hidden-oasis-staff-payroll}"
APP_ENV="${APP_ENV:-/etc/hiddenoasis/staff-payroll.env}"
SERVICE_USER="${SERVICE_USER:-staff-payroll}"
SERVICE_GROUP="${SERVICE_GROUP:-staff-payroll}"
STATE_DIR="${STATE_DIR:-/var/lib/hiddenoasis/staff-payroll}"
DB_PATH="$STATE_DIR/staff_payroll.sqlite"
UPLOAD_DIR="$STATE_DIR/uploads"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/hidden-oasis-staff-payroll/runtime}"
SOURCE_DB="${SOURCE_DB:-$APP_ROOT/data/staff_payroll.sqlite}"
RUNTIME_BASE="${RUNTIME_BASE:-/opt/hiddenoasis/staff-payroll}"
PENDING_ENV="$STATE_DIR/runtime-env.pending"

fail() {
  echo "Fatal: $*" >&2
  exit 1
}

[[ "$(id -u)" == "0" ]] || fail "this preparation must run as root"
[[ -f "$APP_ENV" ]] || fail "env file not found at $APP_ENV"
[[ -f "$SOURCE_DB" ]] || fail "source database not found at $SOURCE_DB"

if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
  groupadd --system "$SERVICE_GROUP"
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd \
    --system \
    --gid "$SERVICE_GROUP" \
    --home-dir /nonexistent \
    --shell /usr/sbin/nologin \
    "$SERVICE_USER"
fi

install -d -o root -g "$SERVICE_GROUP" -m 0750 /opt/hiddenoasis
install -d -o root -g "$SERVICE_GROUP" -m 0750 "$RUNTIME_BASE"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$STATE_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$UPLOAD_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Creating non-live staging copy at $DB_PATH"
  SOURCE_DB="$SOURCE_DB" TARGET_DB="$DB_PATH" python3 - <<'PY'
import os
import sqlite3
from pathlib import Path

source = Path(os.environ["SOURCE_DB"]).resolve()
target = Path(os.environ["TARGET_DB"]).resolve()
target.parent.mkdir(parents=True, exist_ok=True)
source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
target_conn = sqlite3.connect(str(target))
try:
    source_conn.backup(target_conn)
    result = target_conn.execute("PRAGMA integrity_check").fetchone()
    if not result or str(result[0]).lower() != "ok":
        raise SystemExit(f"copied database failed integrity check: {result}")
finally:
    target_conn.close()
    source_conn.close()
PY
else
  echo "Staging database already exists; leaving it unchanged: $DB_PATH"
fi

chown "$SERVICE_USER":"$SERVICE_GROUP" "$DB_PATH"
chmod 0600 "$DB_PATH"
rm -f "$DB_PATH-wal" "$DB_PATH-shm"

cat >"$PENDING_ENV" <<EOF
STAFF_PAYROLL_DB_PATH=$DB_PATH
STAFF_UPLOAD_DIR=$UPLOAD_DIR
STAFF_PAYROLL_BACKUP_DIR=$BACKUP_DIR
EOF
chown root:"$SERVICE_GROUP" "$PENDING_ENV"
chmod 0640 "$PENDING_ENV"

echo "Prepared non-root runtime layout without changing the live environment."
echo "Service account: $SERVICE_USER:$SERVICE_GROUP"
echo "Staging database: $DB_PATH"
echo "Uploads: $UPLOAD_DIR"
echo "Runtime backups: $BACKUP_DIR"
echo "Runtime releases: $RUNTIME_BASE/releases"
echo "Pending env fragment: $PENDING_ENV"
echo "The live env file was not modified and no services were restarted."
