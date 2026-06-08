# Complete Codex Prompt for Accounting, POS, and Operations

Use this prompt after placing all four repositories in one workspace:

- `accounting-program-online`
- `pos-cloud-online`
- `operations-command-center`
- Staff/Payroll repository from this zip

---

You are updating a modular Hidden Oasis business system. Do not merge all apps into one tangled database. Preserve source-of-truth boundaries.

## Source-of-truth boundaries

- **Staff/Payroll** owns employees, attendance, biometric imports, supervisor attendance review, leaves, infractions, memos, staff requests, cash advance ledger, freelance outputs, payroll computation, payslips, 13th month, annual reviews, and payroll approval.
- **Accounting** owns official books, chart of accounts, financial accounts, journals, cashflow, receivables, payables, reconciliations, room folios, PR/PO, supplier bills, and final posted records.
- **POS** owns orders, sales, tenders, refunds, voids, room-charge source records, drawer sessions, cash movements, receipts, and POS sales context.
- **Operations Command Center** is the manager brain only. It owns tasks, department workspaces, requests, approvals, shift notes, guest/fix/post review, operational history, and cross-app status cards. It must not compute payroll, own POS transactions, or post accounting journals.

Do not remove existing functionality. Add integration layers, review queues, idempotency, and tests.

## Staff/Payroll events currently available

The Staff/Payroll app exports JSON payloads using:

```text
external_source = hidden_oasis_staff_payroll
external_id = unique event key
```

Event types:

- `employee.sync`
- `payroll.run.approved`
- `payroll.run.paid`
- `payroll.13th_month.paid`
- `cash_advance.released`
- `cash_advance.repaid`
- `staff.operations.snapshot`
- `payroll.ready_for_owner_review`
- `employee.status.changed`

Accounting must receive accounting-related events. Operations must receive status/review events.

---

# Phase 1 — Accounting repo updates

Repository: `accounting-program-online`

## 1. Add documentation

Create:

```text
docs/PAYROLL_INTEGRATION_CONTRACT.md
docs/ACCOUNTING_REVIEW_QUEUE.md
```

Define payloads, expected outcomes, idempotency, validation errors, replay behavior, and example JSON for:

- `employee.sync`
- `payroll.run.approved`
- `payroll.run.paid`
- `payroll.13th_month.paid`
- `cash_advance.released`
- `cash_advance.repaid`

## 2. Add payroll integration receiver router

Create:

```text
backend/app/api/integrations_payroll.py
```

Register it in:

```text
backend/app/api/__init__.py
```

Prefix:

```text
/api/integrations/payroll
```

Endpoints:

- `POST /api/integrations/payroll/employees`
- `POST /api/integrations/payroll/runs`
- `POST /api/integrations/payroll/13th-month`
- `POST /api/integrations/payroll/cash-advance-release`
- `POST /api/integrations/payroll/cash-advance-repayment`

## 3. Add idempotency storage

Add a model/migration/table if not existing:

```text
integration_receipts
```

Fields:

- id
- external_source
- external_id
- event_type
- source_record_type
- source_record_id
- payload_json
- status: received / accepted / already_applied / rejected / posted / failed
- created_at
- processed_at
- error_message

Unique constraint:

```text
external_source + external_id
```

Duplicate replay must not create duplicate journals/review records.

## 4. Review-first accounting behavior

Imported Staff/Payroll events must create **reviewable accounting records**, not silently posted final books.

Expected journal previews:

### `payroll.run.paid`

- Dr Salaries and Wages Expense
- Cr Salaries Payable
- Dr Salaries Payable
- Cr SSS Payable
- Cr PhilHealth Payable
- Cr Pag-IBIG Payable
- Dr Employer Contributions Expense
- Cr SSS Payable
- Cr PhilHealth Payable
- Cr Pag-IBIG Payable
- Dr Salaries Payable
- Cr Employee Cash Advance Receivable, if cash advance deducted
- Dr Salaries Payable
- Cr Payroll Bank/Cash, for net pay release

### `payroll.13th_month.paid`

- Dr 13th Month Pay Expense
- Cr Payroll Bank/Cash or 13th Month Payable

### `cash_advance.released`

- Dr Employee Cash Advance Receivable
- Cr Cash in Drawer / Bank / GCash

### `cash_advance.repaid`

- Dr Salaries Payable
- Cr Employee Cash Advance Receivable

## 5. Do not keep simplified Accounting payroll as final engine

If Accounting has existing payroll computation, preserve it as legacy/internal, but the Staff/Payroll module is the stronger future payroll engine. Accounting receives approved outputs.

## 6. Tests

Add tests for:

- valid payroll import
- duplicate replay
- invalid payload rejection
- review queue creation
- cash advance release
- cash advance repayment
- 13th month import
- employee sync privacy

---

# Phase 2 — POS repo updates

Repository: `pos-cloud-online`

Preserve existing POS ↔ Accounting integration. Do not break sale, refund, void, cash movement, session/reconciliation, or room-charge workflows.

## 1. Add daily operations context endpoint

Create endpoint:

```text
GET /api/reports/daily-ops-context?date=YYYY-MM-DD
```

Return:

- business_date
- gross_sales
- net_sales
- order_count
- void_count
- refund_count
- cash_sales
- gcash_sales
- card_sales
- room_charge_total
- peak_hour, if available
- first_order_time, if available
- last_order_time, if available
- active_register_sessions, if available
- event/function flag, if available later

This endpoint is read-only and must not approve OT or affect payroll.

## 2. Optional staff identity mapping

POS may receive only safe employee identity:

- employee_code
- display_name
- department
- role
- active/inactive

POS must not receive salary, rates, benefits, government IDs, infractions, memos, annual reviews, or payroll amounts.

## 3. Outbox integrity

Every accounting-facing POS event should retain:

- external_source
- external_id
- sync_status
- attempt_count
- last_attempt_at
- last_error

---

# Phase 3 — Operations repo updates

Repository: `operations-command-center`

Operations is the manager brain only. It already has departments, users, tasks, requests, shift notes, approvals, memos, submissions, guests, fixes, posts, docs, routines, and history. Prefer extending existing `Submission`, `Approval`, `Request`, and `Task` workflows rather than creating duplicate workflows.

Use existing permission model:

- owner/admin/manager can view all
- department users see allowed departments
- one person can belong to multiple departments
- staff/lead users land on primary department workspace

## 1. Add external review/status support

Either extend `Submission` or add a new model for external review items with:

- external_source
- external_id
- event_type
- source_app
- source_record_type
- source_record_id
- department_id
- title
- summary
- priority
- status
- payload_json
- linked_task_id
- linked_approval_id

## 2. Add integration endpoints

- `POST /api/integrations/staff/events`
- `POST /api/integrations/accounting/status`
- `POST /api/integrations/pos/status`
- `GET /api/integrations/overview`

## 3. Staff/Payroll events to accept

- `staff.operations.snapshot`
- `payroll.ready_for_owner_review`
- `employee.status.changed`
- `attendance.exception.created`
- `ot.review.pending`
- `leave.request.pending`
- `cash_advance.request.pending`
- `payroll.qa.warning`
- `annual_review.due`
- `memo.acknowledgment.pending`

## 4. Accounting status events to accept

- `purchase_request.pending`
- `payroll_import.pending_review`
- `pos_sales_import.pending_review`
- `drawer_reconciliation.pending`
- `cash_advance_accounting.pending`
- `payable.due`
- `receivable.issue`

## 5. POS status/context events to accept

- `daily_sales_context`
- `drawer_variance.alert`
- `room_charge.pending_frontdesk_post`
- `refund.review_needed`
- `void.review_needed`

## 6. Dashboard cards

Add cards for:

- Staff on duty today
- Attendance exceptions
- OT pending
- Leave pending
- Cash advance pending
- Payroll QA warnings
- Payroll ready for owner review
- POS sales/order count
- Room-charge pending
- Drawer variance
- Accounting import queue
- Pending PR/PO/accounting approvals

## 7. Actions

- Operations can create tasks/approvals from imported events.
- If an imported event is approved/rejected in Operations, send a callback to the source app later.
- Do not directly mutate source records unless using the source app’s official API.
- Buying/payment requests approved in Operations must link to official Accounting PR/expense records, not duplicate them.

## 8. Shared employee directory cache

Add safe employee cache fields:

- employee_code
- display_name
- role
- department
- active
- source_staff_id

Do not store:

- salary/rates
- benefits
- government numbers
- payroll amounts
- private HR notes
- sensitive infraction details

---

# Phase 4 — Account mapping settings

Accounting should have configurable mappings for:

- Salaries and Wages Expense
- Salaries Payable
- Payroll Bank/Cash
- SSS Payable
- PhilHealth Payable
- Pag-IBIG Payable
- Employer Contributions Expense
- Employee Cash Advance Receivable
- 13th Month Pay Expense
- Cash in Drawer
- GCash / Bank / Card clearing accounts

Avoid hardcoded account IDs if mapping settings exist.

---

# Phase 5 — Non-breaking requirements

Do not remove or break existing functionality.

Preserve Accounting:

- auth
- dashboard
- people
- stock
- payroll legacy routes
- journals
- menu
- approvals
- cashflow
- financial accounts
- transfers
- reconciliations
- receivables
- payables
- purchase requests/orders/receiving
- chart of accounts
- account mappings
- guests
- room folios
- roles/permissions
- system settings
- POS integration routes

Preserve POS:

- order creation
- payments/tenders
- split tenders
- refunds
- voids
- room charges
- drawer sessions
- cash movements
- reconciliation
- outbox integration

Preserve Operations:

- departments
- tasks
- requests
- shift notes
- guest notes
- fixes
- posts
- approvals
- memos
- submissions
- history
- login and department access

---

# Final expected result

1. Staff/Payroll exports approved/paid payroll, 13th month, cash advance, employee sync, and Operations dashboard payloads.
2. Accounting receives financial payroll events idempotently into review queue.
3. POS exposes daily sales/order context for OT and management review.
4. Operations shows cross-app management status without duplicating payroll/accounting/POS logic.
5. Existing POS ↔ Accounting integration remains intact.
6. No working functionality is removed.
