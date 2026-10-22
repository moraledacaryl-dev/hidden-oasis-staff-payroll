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
- `delivered_not_necessarily_posted_count`: Staff-outbox delivery, **not proof of Accounting posting**.
- `backup_metadata.backup_verified=false`: intentional; metadata alone never certifies restoration, attachment recovery, offsite parity, or encryption-key usability.

Review historical outbox candidates against receipts, actual bank/GCash cash flow, employee advance ledgers and Accounting's worklist **before** any future controlled posting decision. Missing Staff outbox events alone are not instructions to replay them; duplicate Accounting transactions are a material risk.

## Required independent closeout

A complete production certification still needs the deployment marker and running API SHA to match, all Staff services healthy, a tested recoverable encrypted backup and offsite/restore-drill evidence, an operator-reviewed reconciliation of flagged financial receipts and statutory remittances, and independent confirmation of paid payroll totals. Complete those checks without altering original paid payroll history.

Staff-to-Accounting transaction imports remain **deferred** until specifically reauthorized.
