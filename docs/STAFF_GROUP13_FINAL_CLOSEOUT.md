# Group 13 — Staff & Payroll final read-only certification

## Scope

This closeout consolidates the existing immutable Staff payroll financial audit with the Staff cash-advance manual repayment UI/outbox projection audit **on the same SQLite read transaction**. The local records may still have unresolved independent evidence; **a passing Staff ledger is not equivalent to a paid bank disbursement, accepted Accounting journal, employee statutory withholding confirmation, or official agency remittance**.

Production must not be called fully certified solely because automated test suites and health checks pass. This script intentionally returns `review_required` even when local source arithmetic and projection are internally consistent. No import, remittance, repayment, reversal, backfill, payroll edit or mutation is authorized.

## Guarded execution on production

1. Confirm the currently deployed exact SHA through the existing GitHub Actions deployment certification and backup/rollback logs. Keep the latest encrypted backup and recent restore drill in force. Do not disable the offsite backup warning unless a verified independent offsite copy exists.
2. Run the audit from the deployed, verified Staff code checkout against the exact existing absolute production database path. **Do not copy local demo data or create replacement databases.** Access through the existing production service environment; do not send credentials or employee details into chat.
3. Review the output privately. Employee item amounts, payor receipts and agency payment evidence must be independently checked by an authorized operator.

```bash
cd /root/repos/hidden-oasis-staff-payroll

# Use the actual configured Staff production database path; no guessing.
python3 scripts/certify_staff_operational_closeout.py \
  --db "$STAFF_PAYROLL_DB_PATH" \
  --backup-dir "$STAFF_PAYROLL_BACKUP_DIR" \
  --limit 10
```

The command opens the SQLite DB using `mode=ro`, enables `PRAGMA query_only`, starts one read transaction, and does not write any SQL rows, request changes over HTTP, enqueue Staff integrations, or create backups. Exit **2** means a local blocker; exit **1** means non-blocking but unresolved independent evidence. It **never returns zero** or claims full operational certification.

### Optional release-identity evidence

Use only an already-authorized **authenticated** production health JSON export from `GET /api/v1/production/health`, kept private on the operator workstation/VPS. Pass the exact 40-character SHA that the deployed CI/release workflow certified:

```bash
python3 scripts/certify_staff_operational_closeout.py \
  --db "$STAFF_PAYROLL_DB_PATH" \
  --backup-dir "$STAFF_PAYROLL_BACKUP_DIR" \
  --expected-sha "YOUR_CERTIFIED_40_CHARACTER_RELEASE_SHA" \
  --live-health-json "/secure/operator/prod-health.json"
```

The report only displays sanitized SHA identity and status; it does not echo the health payload, employee names, receipt numbers, API keys or storage locations. A matching JSON response still requires its origin to be independently established. A mismatched SHA/health state is a blocker, not a success.

## Minimum closeout evidence

| Dimension | Automated evidence | Remaining independent operator evidence |
|---|---|---|
| Payroll source arithmetic and Paid revisions | Consolidated immutable ledger audit | Original payslips, disbursement records and superseded-run justification |
| Monthly statutory allocation | Existing saved item/snapshot review, date-neutral calendar buckets and cutoff transition review | Historical contribution policy, enrollment and SSS/PhilHealth/Pag-IBIG receipts |
| Cash advance repayments | Staff source/outbox/UI projection parity | Cash drawer, bank or GCash receipts, and Accounting intake/posting |
| Application release | Exact merged SHA, passing CI and guarded deployment, live health identity if supplied | Web/API/worker runtime parity and owner workflow acceptance |
| Business continuity | Encrypted local backup and restore-drill checks from guarded preflight | Offsite copy integrity and restoration at a genuinely independent destination |
| Browser coverage and access security | CI test logs and cross-role responsive screenshots | Any field/device operation not exercised by automated tests |

**Known historical review baseline:** Previous checks identified five manual repayment cases totaling ₱10,500 with missing original Staff outbox evidence and unusual historical statutory cutoff allocation patterns. These are historical observations, not hardcoded expected values; rerun the live read-only tools to obtain current counts. No Accounting imports are authorized.

## Closeout policy

The final production release can be technically healthy while financial and business-continuity evidence remains unresolved. Report these separately. Keep Paid runs immutable; use controlled reviewed correction procedures only after independent source evidence and explicit authorization. Never infer agency settlement from Staff remittance rows or Accounted/Completed delivery statuses.
