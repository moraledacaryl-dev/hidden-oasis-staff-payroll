# Staff and Payroll Integration Outbox

Staff and Payroll is the source of truth for employee identity, schedules, attendance, leave, cash advances, and payroll. Cross-application delivery is asynchronous and never occurs inside the user-facing request path.

## Delivery model

1. A Staff business transaction writes its domain change.
2. The same SQLite transaction inserts or updates an `integration_outbox` event.
3. `scripts/run_integration_worker.py` claims due events in short `BEGIN IMMEDIATE` transactions.
4. The worker sends the event to the destination-specific receiver.
5. Successful and duplicate-safe responses mark the event `Completed`.
6. Network errors, timeouts, HTTP 408/425/429, and HTTP 5xx responses retry with exponential backoff.
7. Contract/authentication HTTP 4xx responses become `Dead Letter` so they cannot retry forever.
8. An Owner may inspect and retry non-completed events through `/api/v1/integrations`.

Staff actions do not wait for Accounting, Operations, POS, or Inventory to be online.

## Statuses

- `Pending`
- `Processing`
- `Retry`
- `Completed`
- `Dead Letter`

Completed events are immutable. Unconfigured destinations remain queued as `Retry`; events are not discarded.

## Idempotency

The sender guarantees uniqueness by:

```text
destination + external_source + external_id
```

Receivers must also enforce their own idempotency. A receiver response with HTTP 409 or JSON status `already_applied` is treated as successful delivery.

## Envelope

```json
{
  "external_source": "hidden_oasis_staff_payroll",
  "external_id": "employee-sync:42:2026-07-13T10:00:00",
  "event_type": "employee.sync",
  "source_record_type": "Employee",
  "source_record_id": 42,
  "generated_at": "2026-07-13T10:00:00+08:00",
  "schema_version": "2026-06-v1",
  "payload": {}
}
```

## Destination authentication

Each destination uses a separate secret. The worker sends both headers during the compatibility rollout:

```text
Authorization: Bearer <destination secret>
X-Integration-Api-Key: <destination secret>
```

Required environment pairs:

```text
STAFF_PAYROLL_ACCOUNTING_SYNC_URL
STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN
STAFF_PAYROLL_OPERATIONS_SYNC_URL
STAFF_PAYROLL_OPERATIONS_SYNC_TOKEN
STAFF_PAYROLL_POS_SYNC_URL
STAFF_PAYROLL_POS_SYNC_TOKEN
STAFF_PAYROLL_INVENTORY_SYNC_URL
STAFF_PAYROLL_INVENTORY_SYNC_TOKEN
```

Do not commit real secrets. Do not use one shared secret for all destinations in production.

## Current event routing

### Accounting

- `employee.sync`
- `payroll.run.approved`
- `payroll.run.paid`
- `payroll.13th_month.paid`
- `cash_advance.released`
- `cash_advance.repaid`

### Operations

Staff operational events use `/api/integrations/staff/events`. Destination receiver completion is part of integration Pass 2.

### POS and Inventory

During the initial rollout, POS and Inventory accept only `employee.sync`. Their receiver endpoints are completed in integration Pass 2.

## Privacy boundary

`employee.sync` contains only:

- employee code
- display name
- department
- position
- employment type/operational role
- active status
- primary department
- Staff source ID

Never place passwords, MFA data, sessions, salary rates, government numbers, private HR records, disciplinary narratives, medical information, or payroll calculations in employee synchronization payloads.

## Worker deployment

Install the systemd template and enable it only after the environment file is configured:

```bash
sudo cp deployment/hiddenoasis-staff-integration-worker.service \
  /etc/systemd/system/hiddenoasis-staff-integration-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now hiddenoasis-staff-integration-worker.service
sudo systemctl status hiddenoasis-staff-integration-worker.service --no-pager
```

The default worker interval is 10 seconds and the default batch size is 25.

## Administrative API

```text
GET  /api/v1/integrations/status
GET  /api/v1/integrations/events
GET  /api/v1/integrations/events/{id}
POST /api/v1/integrations/events/{id}/retry
POST /api/v1/integrations/process
```

The status and event views are limited to Owner and Payroll roles. Manual retry and processing are Owner-only.
