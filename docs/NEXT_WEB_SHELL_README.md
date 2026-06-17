# Hidden Oasis Staff Payroll — Next.js Web Shell

This is the first production-grade Next.js shell for the Staff Payroll migration.

It is intentionally separate from the Streamlit app and the FastAPI wrapper:

```text
Streamlit app        remains fallback
FastAPI wrapper      reads current SQLite and calls Python payroll engine
Next.js web shell    presents role-based production UI
```

## Safety Boundary

This web shell:

- does not replace Streamlit
- does not modify the database
- does not calculate payroll in JavaScript/TypeScript
- does not save payroll drafts
- does not approve/pay/lock payroll
- does not migrate SQLite to PostgreSQL

Payroll preview comes from the FastAPI endpoint:

```text
POST /api/v1/payroll/preview
```

That endpoint uses the existing Python payroll engine.

## Pages Added

```text
/             Owner command center
/staff        Staff directory
/supervisor   Supervisor action queue
/payroll      Payroll preview and QA
/owner        Owner approval cockpit
/reports      Report foundation
/settings     Migration controls
```

## Run the FastAPI Wrapper First

From repo root:

```bash
cd /root/repos/hidden-oasis-staff-payroll
. .venv-api/bin/activate
python -m uvicorn api.server_review:app --host 127.0.0.1 --port 8001
```

Leave that terminal open.

## Install and Run the Web Shell

Open a second terminal:

```bash
cd /root/repos/hidden-oasis-staff-payroll/apps/web
cp .env.example .env.local
npm install
npm run dev
```

The web app runs at:

```text
http://SERVER_IP:3001
```

For this server:

```text
http://89.167.28.163:3001
```

## Environment Variables

```bash
STAFF_PAYROLL_API_URL=http://127.0.0.1:8001
```

If the API process uses `STAFF_PAYROLL_API_KEY`, set it only server-side:

```bash
STAFF_PAYROLL_API_KEY=<same-private-key-as-api>
```

## Verification Checklist

Before adding any write endpoints, verify:

1. `/` loads command center.
2. `/staff` shows 15 employee records from the API.
3. `/payroll` shows the same preview totals as the API smoke test.
4. The preview displays `preview_only_no_save`.
5. Streamlit payroll preview for the same cutoff matches the API/Next totals.

Known test cutoff from the first successful API run:

```text
2026-06-01 to 2026-06-15
Gross pay: 112,851.06
Net pay: 90,563.00
Total deductions: 22,288.06
Cash advance deduction: 13,500.00
Employees: 15
```

## Next Stage After Verification

Only after the web shell runs and preview totals match Streamlit:

1. Add real authentication/session handling.
2. Add server-side authorization by role.
3. Add write endpoints one workflow at a time:
   - attendance decision
   - OT decision
   - leave decision
   - payroll save draft
   - payroll approve
   - mark paid
   - lock/reopen
4. Add audit log checks for every write.
5. Keep Streamlit as fallback until all production workflows are proven.
