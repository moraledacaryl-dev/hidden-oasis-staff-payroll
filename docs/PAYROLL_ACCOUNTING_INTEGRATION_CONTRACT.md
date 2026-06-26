# Staff/Payroll → Accounting Integration Contract

This contract defines how the Hidden Oasis Staff & Payroll module exports accounting-ready records to the Accounting Program.

## General rules

- `external_source` is always `hidden_oasis_staff_payroll`.
- `external_id` is the idempotency key. Accounting must treat `external_source + external_id` as unique.
- Payroll sends only approved/paid/locked records. Drafts stay inside Staff/Payroll.
- Accounting receives records into a review queue first. It should not silently final-post journals unless an authorized Accounting user approves.
- Amounts are Philippine Peso decimals.
- Dates use `YYYY-MM-DD` when representing business dates.
- Timestamps use ISO text.

## Event types

### 1. `employee.sync`

Purpose: Send operational employee identity to Accounting/POS/Operations without exposing private HR/payroll details.

Payload includes:

- employee_code
- full_name
- department
- position
- employment_type
- status
- supervisor

Must not include salary, government numbers, infractions, memos, benefits, or personal HR notes.

### 2. `payroll.run.approved`

Purpose: Let Accounting preview a payroll run before cash/bank release.

Accounting outcome:

- create/update accounting review queue item
- do not post final journal yet unless approved
- prevent duplicate import by `external_source + external_id`

### 3. `payroll.run.paid`

Purpose: Send paid payroll details and journal preview.

Expected accounting lines:

- Dr Salaries and Wages Expense / Cr Salaries Payable
- Dr Salaries Payable / Cr SSS Payable
- Dr Salaries Payable / Cr PhilHealth Payable
- Dr Salaries Payable / Cr Pag-IBIG Payable
- Dr Employer Contributions Expense / Cr SSS Payable
- Dr Employer Contributions Expense / Cr PhilHealth Payable
- Dr Employer Contributions Expense / Cr Pag-IBIG Payable
- Dr Salaries Payable / Cr Employee Cash Advance Receivable, if payroll deducted advances
- Dr Salaries Payable / Cr Payroll Bank/Cash, for net pay release

### 4. `payroll.13th_month.paid`

Purpose: Send approved/paid 13th month run to Accounting.

Expected accounting lines:

- Dr 13th Month Pay Expense
- Cr Payroll Bank/Cash or 13th Month Payable, depending on Accounting approval flow

### 5. `cash_advance.released`

Purpose: Record release of a staff cash advance.

Expected accounting lines:

- Dr Employee Cash Advance Receivable
- Cr Cash in Drawer / Bank / GCash, depending on release method

If released from drawer, it should link to the drawer cash-out movement. Do not record it again as a separate drawer expense.

### 6. `cash_advance.repaid`

Purpose: Record payroll repayment against outstanding staff cash advance.

Expected accounting lines:

- Dr Salaries Payable
- Cr Employee Cash Advance Receivable

## Replay / idempotency rules

Accounting must return:

- `accept` when it creates the review record
- `already_applied` when `external_source + external_id` already exists
- `reject` when payload is invalid
- `retryable_failure` for server/network problems

## Current transport

V6 exports payloads as JSON files in a ZIP from the **Accounting Sync** page. Later, the same JSON shapes can be sent directly to Accounting API endpoints.
