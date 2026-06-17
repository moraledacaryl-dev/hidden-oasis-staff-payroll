# Staff Payroll API Wrapper

This is the first production-migration API layer for the Hidden Oasis Staff Payroll app.

It is intentionally conservative:

- It does not replace the Streamlit app.
- It does not rewrite payroll formulas.
- It does not migrate the database.
- It does not save payroll runs yet.
- Payroll preview uses the existing `core/payroll_engine.py` engine.
- Database reads use the existing SQLite database unless `STAFF_PAYROLL_DB_PATH` is set.

## Install API Dependencies

From the repo root:

```bash
python3 -m pip install -r requirements-api.txt
```

If you also need the original Streamlit app dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Run Locally

```bash
python3 -m uvicorn api.server_review:app --host 127.0.0.1 --port 8001 --reload
```

Open:

```text
http://127.0.0.1:8001/docs
```

## Optional Environment Variables

```bash
export STAFF_PAYROLL_DB_PATH="data/staff_payroll.sqlite"
export STAFF_PAYROLL_API_KEY="change-this-before-production"
export STAFF_PAYROLL_CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
```

When `STAFF_PAYROLL_API_KEY` is set, requests must include:

```text
X-API-Key: change-this-before-production
```

When `STAFF_PAYROLL_API_KEY` is not set, the API allows local testing without an API key.

## Current Endpoints

```text
GET  /health
GET  /api/v1/meta
GET  /api/v1/staff/employees
GET  /api/v1/staff/employees/{employee_id}
GET  /api/v1/schedules
GET  /api/v1/time-logs
GET  /api/v1/payroll/preflight
POST /api/v1/payroll/preview
```

## Preview Payroll Without Saving

Example:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/payroll/preview \
  -H 'Content-Type: application/json' \
  -d '{"period_start":"2026-06-01","period_end":"2026-06-15"}'
```

If an API key is configured:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/payroll/preview \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-this-before-production' \
  -d '{"period_start":"2026-06-01","period_end":"2026-06-15"}'
```

## Safety Boundary

The current API is a read/preview wrapper. It should be used to verify that the future Next.js frontend can safely read the current data and request payroll previews from the existing engine.

Write endpoints such as save draft, approve payroll, mark paid, lock, reopen, cash advance approval, leave approval, and attendance approval should be added only after preview outputs are verified against the Streamlit app.

## Next Migration Step

After this API starts successfully:

1. Pull it on the server.
2. Install `requirements-api.txt`.
3. Run the API on localhost.
4. Test `/health`, `/api/v1/meta`, and `/api/v1/payroll/preview`.
5. Compare payroll preview totals with the Streamlit payroll preview for the same cutoff.
6. Only then add the first Next.js frontend shell.
