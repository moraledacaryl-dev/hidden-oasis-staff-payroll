# Hidden Oasis Staff Payroll

Staff operations and payroll system for Hidden Oasis.

## Scope

- Employee records and account access
- Weekly schedules, publication, acknowledgements, and shift requests
- Attendance review, overtime approval, leave, and HR records
- Cash advances and repayment history
- Payroll preview, controlled runs, corrections, payslips, and reports
- Audit logs, production health, encrypted backups, and off-server copies

Accounting remains the owner of the general ledger. POS and Operations receive only the integration data intended for them.

## Roles

- **Owner:** full access, user administration, payroll approval, backups, and system settings
- **Payroll Admin:** payroll preparation, employee payroll fields, HR, schedules, and production health
- **General Manager:** schedules, attendance, HR, performance, cash advances, payslip distribution, and operational reports
- **Staff:** own schedule, shift requests, leave requests, attendance, HR records, cash advances, and payslips

The internal role key for General Manager remains `supervisor` for compatibility with existing records and integrations.

## Local Setup

```bash
python3 -m venv .venv-api
.venv-api/bin/python -m pip install -r requirements-api.txt
cd apps/web
npm ci
cd ../..
```

Create or reset the owner account:

```bash
.venv-api/bin/python scripts/bootstrap_owner.py --name "Owner"
```

Run the API:

```bash
STAFF_PAYROLL_API_KEY=<local-api-key> \
STAFF_PAYROLL_SESSION_SECRET=<long-random-secret> \
.venv-api/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001 --reload
```

Run the web app in another terminal:

```bash
cd apps/web
STAFF_PAYROLL_API_URL=http://127.0.0.1:8001 \
STAFF_PAYROLL_API_KEY=<local-api-key> \
npm run dev
```

Open `http://127.0.0.1:3001`.

## Production Environment

Required:

```text
STAFF_PAYROLL_ENV=production
STAFF_PAYROLL_API_KEY=<long-random-secret>
STAFF_PAYROLL_SESSION_SECRET=<different-long-random-secret>
STAFF_PAYROLL_DB_PATH=/absolute/path/staff_payroll.sqlite
STAFF_PAYROLL_CORS_ORIGINS=https://staff.example.com
STAFF_PAYROLL_API_URL=http://127.0.0.1:8001
```

Recommended:

```text
STAFF_PAYROLL_BACKUP_DIR=/srv/backups/staff-payroll
STAFF_PAYROLL_BACKUP_KEY=<long-random-backup-secret>
STAFF_PAYROLL_OFFSITE_BACKUP_DIR=/mounted-offsite/staff-payroll
STAFF_PAYROLL_BACKUP_RETENTION=30
```

Privileged accounts must set up an authenticator after sign-in. Password resets and role or status changes revoke existing sessions.

## Backups

Create a backup from the owner Backups page or from the command line:

```bash
.venv-api/bin/python scripts/backup_database.py
```

Backups use SQLite's online backup API and are integrity-checked before completion. Set `STAFF_PAYROLL_BACKUP_KEY` to encrypt them. Verification and download are available from the owner Backups page.

## Verification

```bash
PYTHONPYCACHEPREFIX=/tmp/hidden-oasis-pycache \
.venv-api/bin/python -m compileall -q api core scripts tests
.venv-api/bin/python -m unittest discover -v
cd apps/web
npm run lint
npm run typecheck
npm run build
```

The test suite covers authentication, MFA, lockouts, migrations, backups, API contracts, shift swaps, leave workflows, payroll rules, corrections, and integration payloads.

## Deployment

```bash
cd /root/repos/hidden-oasis-staff-payroll
git pull --ff-only origin main
.venv-api/bin/python scripts/backup_database.py
.venv-api/bin/python scripts/production_preflight.py
cd apps/web
npm ci
npm run build
systemctl restart hidden-oasis-payroll-api
systemctl restart hidden-oasis-payroll-web
systemctl reload nginx
```

The production API entrypoint is `api.server:app`. Runtime databases, backups, uploads, environment files, and generated builds are ignored by Git.

## Payroll Safety

- `scheduled_shifts` is the editable schedule source; old schedules remain a read-only migration fallback.
- Paid payroll runs are locked.
- Later changes use controlled revisions or payroll corrections.
- Schedule changes are audited and do not silently rewrite saved payroll.
- Government contribution and tax configuration must be checked against current official tables before live payroll.
