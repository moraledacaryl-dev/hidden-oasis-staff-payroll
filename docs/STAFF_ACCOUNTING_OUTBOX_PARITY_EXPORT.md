# Staff financial outbox → Accounting: confidential read-only source snapshot

For Accounting [integration acceptance #334](https://github.com/moraledacaryl-dev/accounting-program-online/issues/334), this command exports only source financial event identities, revision and delivery status. No employee names, wages, transaction amounts, private JSON, bank references or API secrets are exported.

```bash
cd /root/repos/hidden-oasis-staff-payroll
python3 scripts/export_accounting_outbox_snapshot.py \
  --db /absolute/path/to/staff-payroll.sqlite \
  --output /root/restricted-staff-accounting-source.json
```

Read-only guarantees: SQLite file opened with `mode=ro`, `PRAGMA query_only=ON` and a single read snapshot transaction. It reads all matching `integration_outbox` financial rows without pagination (Staff `employee.sync` and other destinations are deliberately excluded). It derives revision exactly as the Staff Accounting adapter does, and refuses inconsistent or malformed envelopes rather than publishing an incomplete export. The output file is exclusive-creation mode `0600`, cannot overwrite an existing file, and must be kept off public CI logs or downloadable artifacts.

The exported object is directly suitable for the `producers.staff` input of the Accounting offline parity tool `backend/scripts/audit_source_outbox_parity.py`. The field `complete_for_window` defaults to **false**, even though the source database scan is unpaginated. The operator must independently establish equivalent time-window coverage across the Staff and Accounting database snapshots before making completeness assertions.

- `Completed` proves Staff's delivery attempt received a successful acknowledgement; **not** Accounting acceptance, payroll settlement, journal posting, or bank/GCash reconciliation.
- `Pending`, `Processing`, `Retry`, `Dead Letter` and historical states are retained for investigating backlog, not automatically replayed.
- No manual cash-advance repayment outbox backfill is performed. The historical five repayments remain subject to separate documentary review and user-deferral of Accounting postings.
- Never upload this identity file into GitHub, an issue, workflow artifact or public chat. Issue #334 should contain only privacy-safe aggregate results.

This is a local *preparatory exporter*; it is not an automated cross-system acceptance test and does not access Accounting's production database.
