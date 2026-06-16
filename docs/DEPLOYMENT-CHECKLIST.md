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
STAFF_PAYROLL_API_KEY=<set-a-private-key>
STAFF_PAYROLL_SESSION_SECRET=<set-a-long-random-secret>
STAFF_PAYROLL_CORS_ORIGINS=http://89.167.28.163:3001,http://127.0.0.1:3001
```

## 3. API command

```bash
cd /root/repos/hidden-oasis-staff-payroll
. .venv-api/bin/activate
python3 -m uvicorn api.server_review:app --host 127.0.0.1 --port 8001
```

## 4. Web environment

Set the API URL and API key for the Next.js app:

```bash
NEXT_PUBLIC_STAFF_PAYROLL_API_URL=http://127.0.0.1:8001
STAFF_PAYROLL_API_KEY=<same-private-key>
```

## 5. Web command

```bash
cd /root/repos/hidden-oasis-staff-payroll/apps/web
npm install
npm run build
npm run start -- -H 0.0.0.0 -p 3001
```

## 6. Smoke tests

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
