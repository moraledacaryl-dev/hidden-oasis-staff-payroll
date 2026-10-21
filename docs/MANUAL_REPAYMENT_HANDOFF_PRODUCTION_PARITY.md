# Staff Accounting handoff review: production verification

After a guarded Staff deployment, compare the **read-only** Cash Advances
handoff review queue with the canonical Staff repayment and outbox data.

```bash
cd /root/repos/hidden-oasis-staff-payroll
set -a
source /etc/hiddenoasis/staff-payroll.env
set +a
python3 scripts/verify_manual_repayment_review_queue.py \
  --db "$STAFF_PAYROLL_DB_PATH" --limit 0
```

The command opens SQLite in `mode=ro`, sets `PRAGMA query_only=ON`
and reads all data under one transaction snapshot. It exits 0 only if the
source-level repayment and Accounting outbox classifications match the API's
`repayment_history` projection. The summary includes the count and pesos
that should appear in the **Staff Accounting handoff review** card.

For the October 21 baseline, the prior audits reported **five** active
manual repayments missing their Staff Accounting outbox, for **₱10,500**
total. That is a historical baseline, **not** a hardcoded expectation in
this canary; totals can change as future valid repayments occur.

A passing parity check **does not** prove that the web client actually rendered
that value. Visually verify the authenticated Cash Advances page after
deployment, including the filtered `?review=accounting` view. This audit
does not access Accounting's live database, and `Completed` only establishes
delivery, not accepted, journal-posted, or reconciled funds.

If the report fails, **do not backfill, replay, reverse or adjust repayments**:
inspect the projection and source IDs, identify the mismatch, then fix through
a reviewed PR with regression tests. A real financial reconciliation still
requires the original receipt/deposit and cash/bank/GCash evidence.
