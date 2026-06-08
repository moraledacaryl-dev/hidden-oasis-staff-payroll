# Four-App Workspace Integration Plan

## Apps

1. Staff/Payroll — this app
2. Accounting Program — `accounting-program-online`
3. POS Cloud — `pos-cloud-online`
4. Operations Command Center — `operations-command-center`

## Source of truth

| Domain | Source of truth |
|---|---|
| Employee HR/payroll profile | Staff/Payroll |
| Attendance, leaves, OT, memos, infractions | Staff/Payroll |
| Payroll computation, payslips, 13th month | Staff/Payroll |
| Orders, tenders, refunds, voids, drawer sessions | POS |
| Official books, journals, accounts, PR/PO, payables/receivables | Accounting |
| Manager review, tasks, department workspaces, operational approvals | Operations |

## Staff/Payroll → Accounting

Events:

- `employee.sync`
- `payroll.run.approved`
- `payroll.run.paid`
- `payroll.13th_month.paid`
- `cash_advance.released`
- `cash_advance.repaid`

Accounting receives these into a review queue first. It must enforce uniqueness on:

```text
external_source + external_id
```

## Staff/Payroll → Operations

Events:

- `staff.operations.snapshot`
- `payroll.ready_for_owner_review`
- `employee.status.changed`

Operations displays status/review cards and may create tasks/approvals. It does not compute payroll.

## POS → Staff/Payroll / Operations

POS should expose read-only context:

- daily gross/net sales
- order count
- void/refund count
- room-charge total
- drawer variance
- peak hour, if available

This supports OT review and manager context.

## Operations → Accounting

Operations may create or link official Accounting records only after management approval:

- purchase request
- expense request
- reimbursement
- approved cash release handoff

Operations should not post journals.

## Privacy boundary

Operations and POS may receive safe employee identity only:

- employee code
- display name
- department
- position/role
- active/inactive status

Do not sync:

- salary/rates
- benefit eligibility
- government IDs
- detailed payroll lines
- private HR notes
- sensitive infraction details
- annual review details

## Best workflow

```text
Biometric/manual logs in Staff/Payroll
→ Supervisor review and approved OT
→ POS/Operations context supports review
→ Payroll is computed and locked in Staff/Payroll
→ Staff/Payroll sends accounting payload
→ Accounting receives into review queue
→ Accounting posts official books
→ Operations shows status cards across apps
```
