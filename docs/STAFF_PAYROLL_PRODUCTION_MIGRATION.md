# Hidden Oasis Staff Payroll — Production Migration Guardrails

This document records the required migration order for moving the Staff & Payroll app from the current Streamlit local prototype toward a production-grade Next.js interface without losing payroll correctness or current data.

## Core Rule

Do not do a big-bang rewrite.

The current Streamlit app and its Python payroll logic remain the source of truth until the new Next.js + API system proves it produces the same payroll results on copied data.

## Required Migration Order

1. Freeze the current Streamlit app.
   - Treat the current app as the working source of truth.
   - Do not delete the Streamlit app.
   - Do not rewrite payroll formulas yet.
   - Do not rewrite database schema first.

2. Back up the current SQLite database.
   - Protect `data/staff_payroll.sqlite`.
   - Create a timestamped copy of the database.
   - Export all tables to CSV.
   - Export database schema.
   - Save a manifest with row counts and file hashes.

3. Tag or branch the current stable version.
   - Suggested tag/branch name: `streamlit-stable-before-next-migration`.
   - This is the rollback point if later migration steps fail.

4. Add a Python API around existing logic.
   - Use FastAPI or equivalent.
   - Keep SQLite at this stage.
   - The API should reuse existing Python payroll modules instead of duplicating payroll formulas in JavaScript/TypeScript.
   - Next.js must call the API; Next.js must not calculate payroll itself.

5. Build the Next.js frontend.
   - Build role-based portals:
     - Staff portal
     - Supervisor portal
     - Payroll admin portal
     - Owner dashboard
     - Reports/settings
   - The first goal is better UI/UX, not formula changes.

6. Connect Next.js to the Python API.
   - API remains the payroll and database boundary.
   - Next.js is the presentation layer.
   - All sensitive payroll actions must be checked server-side.

7. Test using a copied database.
   - Never use the only real database for migration testing.
   - Compare output against the current Streamlit app.
   - Verify at least:
     - regular pay
     - night differential
     - overtime approval
     - rejected or pending attendance
     - leave with pay
     - leave without pay
     - cash advance deduction
     - freelance output pay
     - semi-monthly cutoff behavior
     - 13th month computation
     - payslip totals

8. Run Streamlit and Next.js side by side.
   - Streamlit remains fallback.
   - Next.js becomes the preferred interface only after successful comparison.

9. Migrate SQLite to PostgreSQL only after the UI/API is stable.
   - Export from SQLite.
   - Import into PostgreSQL.
   - Compare table row counts.
   - Compare sample payroll outputs.
   - Keep rollback copies.

10. Retire Streamlit last.
    - Retire it only when Next.js + API + production database are proven stable.

## What AI Can Safely Do

AI can safely perform these tasks in GitHub without touching real data:

- Add migration documentation.
- Add backup/export scripts.
- Add FastAPI skeleton files.
- Add Next.js frontend structure.
- Add API client code.
- Add role-based UI components.
- Add tests for payroll behavior.
- Add SQLite-to-PostgreSQL migration scripts.
- Review diffs and identify risky changes.

## What Caryl Must Personally Control

Caryl must personally control these tasks:

- Keep a copy of the real database file.
- Run backup/export scripts on the real machine/server.
- Keep secrets private:
  - database passwords
  - API keys
  - admin passwords
  - deployment tokens
  - email credentials
- Confirm government/payroll assumptions with accountant/bookkeeper where needed:
  - SSS table
  - PhilHealth
  - Pag-IBIG
  - withholding tax
  - holiday pay
  - night differential
  - 13th month inclusions/exclusions
- Provide actual biometric device export files before final biometric parser work.
- Approve final staff/supervisor/payroll/owner permissions.
- Test real staff cases before production use.

## Do-Not-Break List

The following behavior must be preserved until deliberately revised and retested:

- Actual approved hours as payroll basis.
- 9-hour normal shift equals 8 paid hours plus 1 unpaid break where applicable.
- Security can have zero break when configured.
- Overtime is paid only when approved.
- Pending or disputed attendance should block or warn before payroll approval.
- Payroll runs must support draft/review/approve/paid/lock/reopen flow.
- Locked payroll must not be silently overwritten.
- Cash advance deductions must not exceed available net pay.
- Payslip and 13th month outputs must remain available.
- Accounting/operations sync must remain reviewable and auditable.

## Immediate Safe Next Steps

1. Run the backup/export script locally or on the server.
2. Confirm that the generated backup folder contains:
   - SQLite copy
   - CSV exports
   - schema file
   - manifest file
3. Create a stable tag/branch after backup.
4. Start API wrapper work without changing formulas.
5. Start Next.js UI shell after API routes exist.
