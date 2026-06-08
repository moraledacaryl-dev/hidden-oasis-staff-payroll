# Staff/Payroll API Integration Payloads

All Staff/Payroll outbound events use this envelope:

```json
{
  "external_source": "hidden_oasis_staff_payroll",
  "external_id": "stable-idempotency-key",
  "event_type": "event.name",
  "source_record_type": "Payroll Run",
  "source_record_id": 123,
  "generated_at": "2026-06-08 10:30:00",
  "schema_version": "2026-06-v1",
  "payload": {}
}
```

`external_source + external_id` is the idempotency key. Receivers must create review records first and must not directly compute payroll, edit POS sales, or post accounting journals.

## Accounting Events

- `employee.sync`: `payload.employees[]` contains only `employee_code`, `display_name`, `department`, `position`, `role`, `active`, `primary_department`, `source_staff_id`. It must never include salary, rates, benefits, government IDs, payroll amounts, infractions, annual reviews, or HR notes.
- `payroll.run.approved`: `payload.run`, `payload.totals`, `payload.items`, and `payload.journal_preview` for Accounting review before payment.
- `payroll.run.paid`: same shape as approved, with employer contributions (`sss_er`, `sss_ec`, `philhealth_er`, `pagibig_er`), employee deductions, cash advance deduction, and net pay release preview.
- `payroll.13th_month.paid`: `payload.employee`, `payload.run`, `payload.lines`, and a 13th month pay journal preview.
- `cash_advance.released`: `payload.employee`, `payload.cash_advance`, optional `payload.drawer_movement`, and debit Employee Cash Advance Receivable / credit cash-bank-GCash preview.
- `cash_advance.repaid`: `payload.employee`, `payload.cash_advance`, `payload.repayment`, and debit Salaries Payable / credit Employee Cash Advance Receivable preview.

## Operations Events

- `staff.operations.snapshot`: `payload.counts` only. Counts include staff on duty today, attendance exceptions, OT pending, leave pending, cash advances pending, payroll QA warnings, payroll ready for owner review, annual reviews due, and memo acknowledgments pending.
- `payroll.ready_for_owner_review`: safe run metadata plus QA summary. Operations may create tasks or approvals, but final approval stays in Staff/Payroll.
- `employee.status.changed`: safe identity fields only, matching `employee.sync`.
- `attendance.exception.created`: safe attendance exception metadata; no pay rates or disciplinary notes.
- `ot.review.pending`: OT hours and operational context needed for manager review.
- `leave.request.pending`: leave type, dates, status, and safe employee identity.
- `cash_advance.request.pending`: request status and safe employee identity; avoid private notes unless manager-entered for review.
- `annual_review.due`: due status and safe employee identity only; no review scores or HR notes.
- `memo.acknowledgment.pending`: memo title/type/status only; do not export memo body when it contains HR notes.

## Environment Placeholders

- `ACCOUNTING_API_BASE_URL`
- `OPERATIONS_API_BASE_URL`
- `POS_API_BASE_URL`
- `INTEGRATION_API_KEY`
