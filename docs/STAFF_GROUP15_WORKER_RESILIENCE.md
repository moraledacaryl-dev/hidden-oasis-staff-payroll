# Group 15 — Integration worker resilience and concurrency evidence

## Fix: avoid batch-wide Processing stranding

The previous worker claimed up to 25 events before sending the first HTTP request. If a deployment restart, process failure, or unhandled exception interrupted the worker, **every unattempted event remained `Processing`** even though it had never reached a destination.

Both the canonical outbox worker and Operations v2 adapter now acquire **one claim immediately before sending that event**. Once it completes or transitions to Retry / Dead Letter, the next claim is acquired. Batch sizes still bound work per loop. This adds database transactions per event but limits ordinary interruption exposure to at most the current in-flight event per worker; the tradeoff is suitable for small resort-scale workloads.

**Important:** A `Processing` row is not proof that its destination received or rejected it. The worker does **not** automatically requeue abandoned in-flight rows; automatic replay could double-post financial receipts.

## Read-only operator diagnostic

An authorized operator can inspect the *actual configured production SQLite file* using:

```bash
python3 scripts/audit_stale_outbox_claims.py --db "$STAFF_PAYROLL_DB_PATH" --stale-minutes 15
```

This opens the existing absolute database read-only and outputs aggregate counts by destination. It does not disclose employee identifiers, source IDs, payloads, paths, API credentials, or event contents.

- Exit `0`: no stale or unknown-age Processing claims found.
- Exit `1`: stale or unparseable Processing claims require manual provenance investigation.
- Exit `2`: database or schema unavailable; do not assume health.

Inspect destination acceptance and idempotency evidence privately before *any* manual retry. Preserve Accounting posting and historical financial reconciliation deferrals. The diagnostic does not mutate the DB or trigger network deliveries.

## Regression evidence

`tests/test_group15_worker_reliability.py` covers worker crashes, preservation of untouched Pending events, batch-limit behavior, multi-connection concurrent claims, successful mocked deliveries, and rollback of source/outbox changes in an interrupted SQLite transaction.

`tests/test_group15_stalled_claim_audit.py` covers stale, recent and unknown timestamps, read-only behavior, privacy, and missing DB fail-closed behavior.

These tests exercise local disposable SQLite and mocked destinations. They are not a substitute for real downstream acknowledgments, production throughput measurements, an independent backup, actual employee payment evidence, or off-server restore acceptance.

## Release gates

Run full Python test suite and standard frontend lint, typecheck, build and browser smoke. Merge only after verified branch CI, then require exact main-SHA green CI and the existing guarded backup / restore-drill / rollback production deployment. Do not write or replay financial events during rollout.
