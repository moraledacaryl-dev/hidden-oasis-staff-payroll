# Staff & Payroll — read-only financial certification

## Purpose and limits

Run the consolidated audit against the **live Staff SQLite database** after deploying a certified release. This report detects local financial inconsistencies and produces human-review queues. It **does not** prove a payroll bank transfer occurred, that a manual receipt was deposited, that Accounting accepted a Staff event, or that SSS / PhilHealth / Pag-IBIG received an actual remittance.

No financial imports, corrective journal entries, payments, reversals, receipt replays, automated settlement, backups, or migrations are performed by this command.

## Running on the production VPS

Use the existing deployed checkout and the **exact database path** configured for the Staff service. Do not paste encryption keys, API secrets, employee details, or receipt references into a chat.

```bash
cd /root/repos/hidden-oasis-staff-payroll
git rev-parse HEAD
readlink -f /opt/hiddenoasis/staff-payroll/current
df -h /

# Use the pre-existing production environment configuration.
# If the variable is not already set, pass the actual Staff database path via --db.
python3 scripts/certify_financial_readiness.py --db "$STAFF_PAYROLL_DB_PATH" --limit 10
```

The command requires an existing **absolute** SQLite database path and opens it using SQLite `mode=ro` and `PRAGMA query_only=ON`. If the service environment is not sourced in the shell, identify the real database path from the service configuration and pass it with `--db`; do not guess or create a new database.

Optional `--backup-dir /absolute/path` reads backup **metadata only**. Optional `--strict-review` returns a nonzero exit status for human-review queues. Without it, exit 0 means **no automated blockers**, not that all outstanding payments are reconciled; exit 2 means a local integrity blocker.

## Read the results

- `blocking_checks`: database-integrity failures, missing schema or audit, and material payroll arithmetic discrepancies. Do not call the ledger certified if any blocker remains.
- `human_review_checks`: suspicious revision links, statutory evidence anomalies, manual cash-advance repayments without a completed Staff outbox, potentially reversed paid adjustments, and stale or unencrypted backups. Reconcile each against independent records.
- `recorded_remittances_php_by_program`: amount **recorded in Staff**, **not confirmed agency payment**.
- `recognized_obligations_php_by_program`: SSS/PhilHealth/Pag-IBIG employee + employer amounts represented in statutory snapshots of non-superseded **Paid/Locked** payroll runs; drafts are excluded. The comparison with Staff remittance records is a review queue, **not proof of agency underpayment**. Independently review official agency receipts and any payments historically recorded outside Staff.
- `insufficient_staff_remittance_evidence_for_programs`: programs where recognized obligations exceed Staff remittance entries, requiring external reconciliation before concluding a liability is unpaid.
- `current_paid_or_locked_runs`, `current_paid_or_locked_runs_with_snapshots`, and `current_paid_or_locked_runs_missing_snapshots`: distinguish settled payroll with missing statutory snapshot coverage from genuinely recognized zero liabilities. A Paid/Locked run with payroll items but no statutory snapshots is **human review**, not automatic financial repair. The report lists only run IDs, not employees.
- `payroll_run_status_counts_all` versus `current_payroll_run_status_counts`: compare all historical records to non-superseded runs. `no_paid_or_locked_runs_for_statutory_recognition` means a zero due amount reflects *current run states*, **not proof no statutory contribution is owed**.
- `current_nonsettled_runs_with_paid_at`: highlights legacy status/timestamp conflicts (for example Approved with a paid timestamp). Reconcile source history before reclassifying or paying anything.
- `delivered_not_necessarily_posted_count`: Staff-outbox delivery, **not proof of Accounting posting**.
- `backup_metadata.backup_verified=false`: intentional; metadata alone never certifies restoration, attachment recovery, offsite parity, or encryption-key usability.
- `backup_metadata.offsite_configuration_status`: indicates `directory_configured`, `s3_configured_not_verified`, `s3_configuration_incomplete`, or `not_configured`. The audit checks the **S3 configuration keys** as well as the optional mounted directory, without exposing bucket names, URLs, or credentials. It never asserts offsite-copy parity.
- `backup_restore_and_offsite_evidence_not_verified`: always remains an **independent review gate** for this metadata-only audit; even an otherwise clean local ledger is **not** a disaster-recovery certification.

Review historical outbox candidates against receipts, actual bank/GCash cash flow, employee advance ledgers and Accounting's worklist **before** any future controlled posting decision. Missing Staff outbox events alone are not instructions to replay them; duplicate Accounting transactions are a material risk.

## Required independent closeout

A complete production certification still needs the deployment marker and running API SHA to match, all Staff services healthy, a tested recoverable encrypted backup and offsite/restore-drill evidence, an operator-reviewed reconciliation of flagged financial receipts and statutory remittances, and independent confirmation of paid payroll totals. Complete those checks without altering original paid payroll history.

For backup verification and restore drills use the existing `scripts/production_preflight.py` or `scripts/restore_drill.py` under the production environment after separately checking free space. The restore drill creates temporary files and writes a restore-evidence marker, but does **not** change the live Staff payroll database. The metadata-only financial audit itself does not perform either operation.

Staff-to-Accounting transaction imports remain **deferred** until specifically reauthorized.
