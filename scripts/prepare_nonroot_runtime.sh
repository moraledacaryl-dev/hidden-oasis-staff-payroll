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
  echo "Creating consistent SQLite copy at $DB_PATH"
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
  echo "State database already exists; leaving it unchanged: $DB_PATH"
fi

chown "$SERVICE_USER":"$SERVICE_GROUP" "$DB_PATH"
chmod 0600 "$DB_PATH"
rm -f "$DB_PATH-wal" "$DB_PATH-shm"

APP_ENV="$APP_ENV" \
DB_PATH="$DB_PATH" \
UPLOAD_DIR="$UPLOAD_DIR" \
BACKUP_DIR="$BACKUP_DIR" \
python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["APP_ENV"])
updates = {
    "STAFF_PAYROLL_DB_PATH": os.environ["DB_PATH"],
    "STAFF_UPLOAD_DIR": os.environ["UPLOAD_DIR"],
    "STAFF_PAYROLL_BACKUP_DIR": os.environ["BACKUP_DIR"],
}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
out = []
for line in lines:
    stripped = line.strip()
    matched = False
    for key, value in updates.items():
        if stripped.startswith(f"{key}="):
            if key not in seen:
                out.append(f"{key}={value}")
                seen.add(key)
            matched = True
            break
    if not matched:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        if out and out[-1] != "":
            out.append("")
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

chmod 0600 "$APP_ENV"

echo "Prepared non-root runtime layout."
echo "Service account: $SERVICE_USER:$SERVICE_GROUP"
echo "State database: $DB_PATH"
echo "Uploads: $UPLOAD_DIR"
echo "Runtime backups: $BACKUP_DIR"
echo "Runtime releases: $RUNTIME_BASE/releases"
echo "No services were restarted."
