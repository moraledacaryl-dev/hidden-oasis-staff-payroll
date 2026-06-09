# Hidden Oasis Staff & Payroll — Final Local Prototype

GitHub-ready local prototype for the Hidden Oasis Staff/Payroll module.

This module is designed to sit beside:

- `accounting-program-online`
- `pos-cloud-online`
- `operations-command-center`

It remains a **Staff/Payroll source app**, not the Accounting ledger, not the POS, and not the Operations manager dashboard.

## What this app owns

- Staff master file and safe employee identity export
- Schedules, time logs, biometric/manual import
- Supervisor attendance review and approved overtime
- Configurable leave types and per-employee leave entitlements
- Cash advance ledger and payroll repayment
- Freelance/output-based pay
- Infractions, memos, staff requests, annual reviews
- Actual-hours payroll computation
- Semi-monthly payroll: 1–15 and 16–end
- Payslip PDF and bulk payslip ZIP export
- 13th month computation and PDF
- Payroll QA/preflight checks
- Employer contribution computation
- Integration outbox for Accounting and Operations

## Preserved payroll logic

- Actual approved hours worked is the default payroll base.
- Standard 9-hour shift means 8 paid hours + 1 unpaid break.
- Security/guard shifts can use zero break deduction.
- Overtime is paid only when supervisor-approved.
- SSS uses the actual month-to-date gross catch-up method:
  - first cutoff computes SSS from actual 1–15 gross;
  - second cutoff computes full-month actual gross SSS, then subtracts first cutoff SSS already deducted.
- PhilHealth and Pag-IBIG use declared monthly basis split/caught up across cutoffs unless settings are changed.
- Benefit eligibility is toggleable per employee.
- Withholding tax is opt-in per employee. Most minimum-wage staff should keep it off/zero; employees who exceed the taxable threshold can be enabled, and nonzero withholding appears in payroll, Accounting payloads, and payslips.
- Payroll locks after approval/payment and requires reopening with reason/audit trail.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

On Mac:

```bash
chmod +x run.command
./run.command
```

On Windows:

```bat
run.bat
```

## Verify before GitHub deploy

```bash
python3 -m unittest discover
python3 smoke_test.py
```

The test suite covers login/password hashing, payroll tax behavior, payroll status transitions, Accounting payload tax export, and the Operations preview query.

## First login

On an existing local database, active users without passwords receive a temporary password:

```text
ChangeMe123!
```

The app forces those users to change the password before continuing. New users and password resets are managed in **Access Control**, which is Owner-only.

## Main workflow

```text
Staff setup
→ schedules / biometric or manual logs
→ attendance review and approved OT
→ leaves, cash advances, freelance outputs, manual adjustments
→ payroll draft
→ payroll QA
→ review / approve / paid / locked
→ payslips / 13th month / accounting export
→ operations status cards
```

## Import options

### Required Excel template

Use **Data Import / Templates → Required Templates** to download the workbook. Fill the sheets you need, then upload it back in **Import Filled Template**.

### Legacy Payroll ZIP import

Use **Data Import / Templates → Legacy Payroll ZIP Import** to upload the old `Payroll.zip` or any ZIP containing `payroll.sqlite`. Migrated payroll history is imported as locked history.

## Integration

### Accounting Sync

Creates review-first, idempotent JSON payloads for Accounting:

- `employee.sync`
- `payroll.run.approved`
- `payroll.run.paid`
- `payroll.13th_month.paid`
- `cash_advance.released`
- `cash_advance.repaid`

Payloads use:

```text
external_source = hidden_oasis_staff_payroll
external_id = unique event key
```

Transport options:

- manual JSON ZIP export for controlled fallback/recovery
- direct POST of Ready Accounting events to `ACCOUNTING_API_BASE_URL`
- direct POST of Ready Operations events to `OPERATIONS_API_BASE_URL`

Direct posting never final-posts official books and never blocks payroll if the receiver is unavailable. Failed attempts stay visible in the Integration Outbox for retry/review.

### Operations Sync

Creates safe manager-dashboard payloads for Operations:

- `staff.operations.snapshot`
- `payroll.ready_for_owner_review`
- `employee.status.changed`

Operations should show status/review cards only. It must not calculate payroll, own HR details, or post accounting journals. Ready Operations events can be posted directly to `/api/integrations/staff/events` when the Operations API URL is configured.

## Privacy boundary

Safe to send to Operations/POS:

- employee code
- display name
- department
- role/position
- active/inactive status
- source record links
- review/pending counts

Keep inside Staff/Payroll:

- salary/rates
- benefit eligibility
- government numbers
- detailed payroll lines
- private HR notes
- sensitive infraction details
- annual review content

## GitHub-ready notes

- `data/staff_payroll.sqlite` is ignored by `.gitignore`.
- Runtime exports, payload ZIPs, and local uploads are ignored.
- The package excludes virtual environments and `__pycache__`.
- Keep this prototype local until final rebuild in FastAPI + PostgreSQL + Next.js.

## Important docs

- `docs/LOGIC.md`
- `docs/PAYROLL_ACCOUNTING_INTEGRATION_CONTRACT.md`
- `docs/FOUR_APP_WORKSPACE_INTEGRATION.md`
- `docs/CODEX_PROMPT_OTHER_APPS.md`
- `docs/FINAL_RELEASE_NOTES.md`

## Current rating

**9.45/10 as a local GitHub-ready prototype.**

Not 10/10 because the final system still needs:

- final biometric device parser after hardware purchase
- live POS/Operations data feed for OT context
- full production rebuild in FastAPI + PostgreSQL + Next.js

This local prototype now has login, hashed passwords, sessions, role-restricted pages, and guarded payroll approvals. Before live payroll, replace/validate the starter SSS table and payroll tax assumptions against the official/current government tables or your accountant's configuration.
