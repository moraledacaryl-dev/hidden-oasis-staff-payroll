# Staff/Payroll API Integration Payloads

Staff/Payroll is the source of truth for HR, attendance, leaves, cash advances, payroll, payslips, 13th month, infractions, memos, annual reviews, and payroll QA. Cross-app events are review/status messages only; they do not let receivers compute payroll or edit Staff/Payroll records.

## Standard Envelope

Every outbound event uses:

```json
{
  "external_source": "hidden_oasis_staff_payroll",
  "external_id": "stable-idempotency-key",
  "event_type": "event.name",
  "source_record_type": "Payroll Run",
  "source_record_id": 123,
  "generated_at": "2026-06-08T10:30:00+08:00",
  "schema_version": "2026-06-v1",
  "status": "For Review",
  "payload": {}
}
```

Receivers enforce idempotency with `external_source + external_id`. Duplicate receipts must return `already_applied` and must not overwrite manager/accounting decisions.

## Event Catalog

### `employee.sync`

- Description: safe employee identity propagation.
- Required payload: `employees[]` with `employee_code`, `display_name`, `department`, `position`, `role`, `active`, `primary_department`, `source_staff_id`.
- Privacy boundary: never export salary, rates, benefits, government IDs, payroll values, infractions, annual review content, memo bodies, or HR notes.
- Receiver behavior: Accounting may map to employee/payee references; Operations may map to users without changing credentials; POS may map cashiers.
- Idempotency key: `employee-sync:{source_staff_id}:{updated_at}` for single employee, or a dated/batch key for whole-directory export.
- Failure modes: missing employee code, unsupported schema, sensitive field detected.

### `payroll.run.approved`

- Description: approved payroll run ready for Accounting review, before cash release.
- Required payload: run metadata, totals, employee count, QA summary, journal preview if available.
- Receiver behavior: Accounting creates review item only.
- Idempotency key: `payroll-run:{run_id}:Approved`.
- Failure modes: missing totals, unbalanced preview, duplicate event.

### `payroll.run.paid`

- Description: paid/locked payroll for official accounting review.
- Required payload: `totals.gross_pay`, employee shares, employer shares (`sss_er`, `sss_ec`, `philhealth_er`, `pagibig_er`), cash advance deduction, net pay, and preview lines.
- Receiver behavior: Accounting creates review item and balanced journal preview; no silent posting.
- Idempotency key: `payroll-run:{run_id}:Paid` or `payroll-run:{run_id}:Locked`.
- Failure modes: missing contribution totals, unbalanced preview, duplicate event.

### `payroll.13th_month.paid`

- Description: paid 13th month run.
- Required payload: employee safe identity, run year/period, net 13th pay, preview lines.
- Receiver behavior: Accounting previews Dr 13th Month Pay Expense and Cr Cash/Bank or 13th Month Payable.
- Idempotency key: `13th-month:{run_id}:{status}`.
- Failure modes: missing amount, duplicate event.

### `cash_advance.released`

- Description: approved cash advance released to employee.
- Required payload: safe employee identity, cash advance ID, amount, release method, optional drawer movement link.
- Receiver behavior: Accounting previews Dr Employee Cash Advance Receivable and Cr Cash in Drawer/Bank/GCash.
- Idempotency key: `cash-advance-release:{cash_advance_id}`.
- Failure modes: missing amount/release method, duplicate event.

### `cash_advance.repaid`

- Description: repayment through payroll deduction or approved repayment.
- Required payload: safe employee identity, cash advance ID, repayment ID, amount.
- Receiver behavior: Accounting previews Dr Salaries Payable and Cr Employee Cash Advance Receivable.
- Idempotency key: `cash-advance-repayment:{repayment_id}`.
- Failure modes: missing repayment amount, duplicate event.

### `staff.operations.snapshot`

- Description: counts for Operations dashboard cards.
- Required payload: `counts.staff_on_duty_today`, `attendance_exceptions`, `ot_pending`, `leave_pending`, `cash_advance_pending`, `payroll_qa_warnings`, `payroll_ready_for_owner_review`, `annual_reviews_due`, `memo_acknowledgments_pending`.
- Privacy boundary: counts only; no employee payroll amounts or HR notes.
- Receiver behavior: Operations updates dashboard/review cards.
- Idempotency key: `ops-snapshot:{business_date}` or a controlled snapshot batch key.
- Failure modes: missing counts, duplicate event.

### `payroll.ready_for_owner_review`

- Description: payroll run needs owner/manager review.
- Required payload: safe run metadata and QA summary.
- Receiver behavior: Operations shows a review card; final approval remains in Staff/Payroll.
- Idempotency key: `ops-payroll-ready:{run_id}:{status}`.
- Failure modes: missing run ID, duplicate event.

### `employee.status.changed`

- Description: employee active/inactive or role/status change.
- Required payload: same safe identity fields as `employee.sync`.
- Receiver behavior: Operations updates status visibility; no credential overwrite.
- Idempotency key: `ops-employee-status:{employee_id}:{status}`.
- Failure modes: missing employee code, sensitive fields.

### `attendance.exception.created`

- Description: missing log, disputed log, late/undertime, or needs review.
- Required payload: source time log ID, work date, safe employee identity, exception type.
- Receiver behavior: Operations review card/task if manager acts.
- Idempotency key: `attendance-exception:{time_log_id}`.
- Failure modes: missing source ID, sensitive note content.

### `ot.review.pending`

- Description: detected overtime waiting for supervisor approval.
- Required payload: time log ID, work date, detected OT hours, operational context counts, safe employee identity.
- Receiver behavior: Operations can create task/approval; Staff/Payroll owns OT approval and pay.
- Idempotency key: `ot-review:{time_log_id}`.
- Failure modes: missing OT hours/source ID.

### `leave.request.pending`

- Description: leave request waiting review.
- Required payload: leave request ID, dates, leave type, status, safe employee identity.
- Receiver behavior: Operations visibility/task only; Staff/Payroll owns entitlement/balance.
- Idempotency key: `leave-request:{leave_request_id}:{status}`.
- Failure modes: missing leave type/dates.

### `cash_advance.request.pending`

- Description: staff cash advance needs manager attention.
- Required payload: cash advance ID, request date, amount requested if needed for manager review, release method, safe employee identity.
- Privacy boundary: do not expose private HR notes or unrelated balances.
- Receiver behavior: Operations visibility/task only; Accounting receives release/repayment events separately.
- Idempotency key: `cash-advance-request:{cash_advance_id}:{status}`.
- Failure modes: missing source ID.

### `annual_review.due`

- Description: annual review due/completed status.
- Required payload: employee code, display name, department, due date/status.
- Privacy boundary: no scores, qualitative review, auto-summary content, infractions, or memo bodies.
- Receiver behavior: Operations dashboard/task only.
- Idempotency key: `annual-review-due:{employee_id}:{year}`.
- Failure modes: sensitive review content detected.

### `memo.acknowledgment.pending`

- Description: memo requires acknowledgement.
- Required payload: memo ID, safe title/type/status, safe employee identity if individual.
- Privacy boundary: do not export memo body if HR-sensitive.
- Receiver behavior: Operations reminder/task only.
- Idempotency key: `memo-ack:{memo_id}:{status}`.
- Failure modes: memo body/private HR content included.

## Transport

The current Streamlit prototype exports JSON ZIP payloads from the integration outbox. Direct API posting to Accounting/Operations can be added later using `ACCOUNTING_API_BASE_URL`, `OPERATIONS_API_BASE_URL`, `POS_API_BASE_URL`, and `INTEGRATION_API_KEY`; posting failures must never block payroll and should mark outbox items Failed/Pending Retry.
