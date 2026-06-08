# Final Local Prototype Release Notes

## Version

Hidden Oasis Staff & Payroll — final local prototype package.

## Rating

**9.45/10 for local prototype readiness.**

## What was upgraded from V6

- Added Operations Sync page for `operations-command-center` compatibility.
- Added safe Operations payload builders:
  - `staff.operations.snapshot`
  - `payroll.ready_for_owner_review`
  - `employee.status.changed`
- Added four-app workspace documentation.
- Added GitHub-ready `.gitignore` and `.env.example`.
- Expanded README with source-of-truth boundaries and GitHub push notes.
- Removed runtime bytecode/cache files from the final package.
- Kept Accounting integration outbox and JSON payload ZIP export.

## Preserved from earlier versions

- Staff master file
- Actual-hours payroll
- Semi-monthly cutoffs
- SSS actual month-to-date catch-up method
- PhilHealth/Pag-IBIG declared monthly basis
- Benefit toggles
- Supervisor-approved OT
- Leave types and entitlement balances
- Cash advances and repayments
- Freelance/output-based pay
- Payroll QA
- Payslip PDF and bulk export
- 13th month pay and PDF
- Employer contributions
- Legacy Payroll.zip importer
- Required Excel templates
- Annual reviews and auto-summary
- Infractions, memos, staff requests
- Login with hashed passwords, temporary-password reset, role-restricted pages, and access-control management
- Accounting integration outbox

## Still intentionally not final

- Final biometric device-specific parser
- Direct API POST transport
- Full POS/Operations live data feed
- Production database migrations
- FastAPI/PostgreSQL/Next.js rebuild

## Recommended next step

Push this repository to GitHub as the Staff/Payroll prototype, then create a workspace with:

- `accounting-program-online`
- `pos-cloud-online`
- `operations-command-center`
- this Staff/Payroll repository

Then use `docs/CODEX_PROMPT_OTHER_APPS.md` to update the other apps safely.
