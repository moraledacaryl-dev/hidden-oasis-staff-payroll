# Integration Pass 3 — Verification and Controlled Activation

This runbook verifies the Staff integration without enabling uncontrolled delivery.

## Safety model

- The integration worker is fail-closed unless `STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED=true`.
- The canary uses one synthetic **inactive** employee reference per run.
- The canary does not create payroll, cash-advance, attendance, leave, schedule, or HR transactions.
- Destination secrets are read from environment variables and are never printed.
- A duplicate copy of the same canary event is sent to prove receiver idempotency.
- A request with an invalid secret is sent to prove authentication rejection.
- Accounting remains review-first. No accounting journal is posted by the canary.

## Required destination configuration

```text
STAFF_PAYROLL_ACCOUNTING_SYNC_URL=https://hiddenoasis.app
STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN=<accounting-secret>

STAFF_PAYROLL_OPERATIONS_SYNC_URL=https://operations.hiddenoasis.app
STAFF_PAYROLL_OPERATIONS_SYNC_TOKEN=<operations-secret>

STAFF_PAYROLL_POS_SYNC_URL=https://pos.hiddenoasis.app
STAFF_PAYROLL_POS_SYNC_TOKEN=<pos-secret>

STAFF_PAYROLL_INVENTORY_SYNC_URL=https://inventory.hiddenoasis.app
STAFF_PAYROLL_INVENTORY_SYNC_TOKEN=<inventory-secret>

STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED=false
```

Keep activation disabled during verification.

## 1. Plan-only check

```bash
set -a
source /etc/hiddenoasis/staff-payroll.env
set +a

.venv-api/bin/python scripts/verify_integration_pass3.py
```

This prints configured destination URLs and missing configuration. It sends no requests.

## 2. Execute the canary

```bash
.venv-api/bin/python scripts/verify_integration_pass3.py \
  --execute \
  --confirm 'PASS3 CANARY'
```

Every destination must report:

- `accepted: true`
- `duplicate_safe: true`
- `invalid_secret_rejected: true`
- `ok: true`

The final report must contain:

```json
{"ok": true}
```

## 3. Inspect Staff readiness

Call the authenticated Staff endpoint:

```text
GET /api/v1/integrations/readiness
```

Before activation, the expected state is:

```text
technical_ready: true
activation_enabled: false
ready: false
```

This is intentional. The activation flag is the final manual control.

## 4. Inspect receiver records

Verify the canary's `external_id` in each receiver:

- Accounting payroll integration receipts or review queue
- Operations external review items
- POS `staff_event::<external_id>` receipt and `staff_employee::<employee_code>` reference
- Inventory inbound `IntegrationEvent`

Confirm that only these employee fields were retained:

```text
employee_code
display_name
department
position
role
active
primary_department
source_staff_id
```

## 5. Outage and retry verification

With activation still disabled, run the Staff unit suite. It verifies:

- retry after `5xx`
- exponential backoff scheduling
- immediate dead letter for non-retryable contract errors
- dead letter after maximum attempts
- duplicate completion
- immutable completed events
- atomic claim behavior
- privacy allow-listing

Do not intentionally take production receivers offline merely to test retry behavior.

## 6. Controlled activation order

Activate one destination at a time:

1. Accounting
2. Operations
3. POS
4. Inventory

For each destination:

1. Configure only that destination URL and token.
2. Run the canary for that destination:

```bash
.venv-api/bin/python scripts/verify_integration_pass3.py \
  --destination accounting \
  --execute \
  --confirm 'PASS3 CANARY'
```

3. Inspect the receiver record.
4. Confirm no unexpected fields or duplicate records.
5. Proceed to the next destination.

## 7. Enable delivery

Only after all canaries pass and explicit production approval is given:

```text
STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED=true
```

Then restart the integration worker and confirm:

```text
integration_activation_state enabled=true
```

Do not merge, deploy, enable, or start the production worker as part of code validation alone.

## Rollback

To stop delivery immediately:

```text
STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED=false
```

Restart the worker. Pending events remain durable and can be delivered later. Completed events remain immutable.
