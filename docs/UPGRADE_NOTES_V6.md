# V6 Upgrade Notes

## Added

- Accounting Sync page.
- Integration outbox with `external_source + external_id` idempotency.
- JSON payload builders for:
  - payroll.run.approved
  - payroll.run.paid
  - payroll.13th_month.paid
  - cash_advance.released
  - cash_advance.repaid
  - employee.sync
- Downloadable integration payload ZIP.
- Connection settings placeholders for Accounting, POS, and Operations APIs.
- Staff/Payroll → Accounting integration contract document.
- Automatic integration event creation when payroll is Approved/Paid and when 13th month is Approved/Paid/Locked.

## Still intentionally pending

- Direct HTTP posting to Accounting API.
- Final Accounting receiver endpoints.
- Final biometric hardware parser.
- True production login/security.
- POS/Operations automatic OT context feed.

## Design rule preserved

Staff/Payroll computes and approves payroll. Accounting owns final books. POS owns sales/drawer/order source data. Operations reads statuses and supports decisions.
