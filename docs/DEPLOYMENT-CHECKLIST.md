# Hidden Oasis Staff Payroll Deployment Checklist

This checklist is for moving the migrated FastAPI and Next.js app from manual terminal testing to a stable server setup.

## 1. Pull latest code

```bash
cd /root/repos/hidden-oasis-staff-payroll
git pull --ff-only origin main
```

## 2. API environment

Required runtime values:

```bash
STAFF_PAYROLL_DB_PATH=/root/repos/hidden-oasis-staff-payroll/data/staff_payroll.sqlite
STAFF_PAYROLL_ENV=production
STAFF_PAYROLL_API_KEY=<set-a-private-key>
STAFF_PAYROLL_SESSION_SECRET=<set-a-long-random-secret>
STAFF_PAYROLL_BACKUP_DIR=/srv/backups/staff-payroll
STAFF_PAYROLL_BACKUP_KEY=<set-a-different-long-random-secret>
STAFF_PAYROLL_OFFSITE_BACKUP_DIR=/mnt/offsite/staff-payroll
STAFF_PAYROLL_CORS_ORIGINS=http://89.167.28.163:3001,http://127.0.0.1:3001
```

Generate `STAFF_PAYROLL_SESSION_SECRET` separately from the API key, for example with `openssl rand -hex 32`. Store both values in the service environment file, not in the repository.

## 3. API command

```bash
cd /root/repos/hidden-oasis-staff-payroll
. .venv-api/bin/activate
python3 -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Confirm the systemd unit has the same entrypoint:

```ini
[Service]
EnvironmentFile=/etc/hidden-oasis/staff-payroll.env
ExecStart=/root/repos/hidden-oasis-staff-payroll/.venv-api/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Replace any old `api.server_review:app` reference, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl show hidden-oasis-payroll-api --property=ExecStart
```

## 4. Web environment

Set the API URL and API key for the Next.js app:

```bash
STAFF_PAYROLL_API_URL=http://127.0.0.1:8001
STAFF_PAYROLL_API_KEY=<same-private-key>
```

## 5. Web command

```bash
cd /root/repos/hidden-oasis-staff-payroll/apps/web
npm ci
npm run build
npm run start -- -H 0.0.0.0 -p 3001
```

## 6. Preflight and smoke tests

Run the production preflight with the service environment loaded:

```bash
set -a
. /etc/hidden-oasis/staff-payroll.env
set +a
.venv-api/bin/python scripts/production_preflight.py
```

Open these pages after both services are running:

- `/login`
- `/cutoff`
- `/payroll/runs`
- `/payroll/runs/1`
- `/payroll/runs/1/reports`
- `/payroll/runs/1/audit`
- `/payroll/runs/1/payslips`

## 7. Do not activate release until checked

Before using any paid/release workflow, verify:

- payroll totals match the old app
- payslips match the approved payroll run
- audit page records the expected lifecycle
- staff portal does not expose another employee's data

## 8. Backup before production use

Run a database backup before any real payroll release.
