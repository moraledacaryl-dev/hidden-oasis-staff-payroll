# Test Results

Date: 2026-06-09

## Staff/Payroll

- Command: `PYTHONPYCACHEPREFIX=/tmp/pycache-payroll python3 -m unittest tests/test_payroll_core.py`
  - Result: passed
  - Details: 11 tests passed, including direct Accounting POST, direct Operations POST, safe employee sync, stable idempotency, payroll contribution payloads, operations count-only payloads, and destination filtering so Accounting posting does not mark Operations-only events as errors.
- Command: `PYTHONPYCACHEPREFIX=/tmp/pycache-payroll python3 -m compileall app.py core tests`
  - Result: passed
  - Details: Streamlit app, core modules, and tests compile.
- Command: `PYTHONPYCACHEPREFIX=/tmp/pycache-staff-smoke python3 smoke_test.py`
  - Result: passed
  - Details: database, Operations payload, employee sync, and ZIP export smoke checks passed.
- Command: UI copy scan for final-pass banned phrases in `app.py`, `core`, `docs`, and `README.md`
  - Result: passed for operational UI
  - Details: remaining matches are documentation checklist/prompt wording only, not Staff app screens.

## Not Run

- Full browser/manual Streamlit workflow testing was not run in this shell.
- Live receiver POSTs were not run because production integration secrets and deployed receiver URLs are server-only values.

Next action: set the real `INTEGRATION_API_KEY` in Staff/Payroll settings on the server, then run one controlled Ready event POST to Accounting and one to Operations.
