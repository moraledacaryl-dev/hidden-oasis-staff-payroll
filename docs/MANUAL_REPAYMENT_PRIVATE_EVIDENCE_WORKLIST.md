# Manual repayment evidence checklist — private operator workflow

## Why this exists

The October 21 production audits verified that five historical manual
cash-advance repayments totaling **₱10,500** are reflected correctly in
Staff balances and in the Staff Accounting handoff review queue. However,
none has an exact Staff-to-Accounting source identity, and none has
independently verified receipt/cash-custody evidence.

The read-only cross-application investigation found unrelated room-booking
revenue and guest-damage transactions with similar amounts; they are
**not** repayment evidence.

## Generate a private review CSV (no database changes)

Run on the protected production server **after verifying the script's GitHub
commit and CI**. Do not write this file into the Git checkout, webroot, shared
downloads, or GitHub issue.

```bash
set -euo pipefail
set -a
source /etc/hiddenoasis/staff-payroll.env
set +a
umask 077
mkdir -p -m 700 /root/staff-repayment-evidence
python3 scripts/export_manual_repayment_evidence_worklist.py \
  --db "$STAFF_PAYROLL_DB_PATH" \
  --output "/root/staff-repayment-evidence/manual-repayments-$(date +%Y%m%d-%H%M%S).csv"
```

The script opens the Staff database in SQLite URI read-only mode, requires
an **absolute new output path**, creates the CSV with mode `0600`, rejects
overwrites and spreadsheet formula prefixes, and never prints receipt
references, employee names, sensitive notes, or account numbers. It writes
only the private CSV—**no Staff or Accounting mutations**.

The CSV contains the Staff repayment ID, cash-advance ID, date, amount,
recorded method, whether a Staff reference exists, and handoff status.
Every evidentiary checkbox starts **NOT_REVIEWED** and the reconciliation
decision starts **PENDING_EVIDENCE**. These are *blank fields for a human
reviewer*, not automated approval flags.

## Documentary reconciliation procedure

1. Use the Cash Advances screen to locate the matching employee/advance
   record privately. Match the original receipt by unique reference when
   available, not by amount alone.
2. Confirm actual receiving method (cash, bank, GCash, etc.), who received
   funds, and the cashbook/deposit statement. Staff repayment #30 is
   recorded `Other`: do not assume the receiving account.
3. Reconcile the corresponding Staff deduction/advance ledger to avoid
   counting the same employee repayment through both payroll deduction
   and a manual receipt.
4. Independently reconcile the Accounting intake review, money transaction
   and general ledger. A completed Staff delivery is transport only.
5. Treat Staff repayments #42 and #43, both ₱3,000 on September 18,
   as **two separate cases**. A single Accounting ₱3,000 entry is never
   sufficient evidence of both. Confirm distinct receipts or a documented
   consolidated deposit with a complete composition.
6. Record reviewer, review date, private evidence location and decision.
   Do not enter confidential reference numbers into tickets or chat.
   Keep the completed CSV restricted to authorized financial personnel.

**No auto-replay, historical balance changes, journal posting, or cash
book correction** should follow solely from this export. Any eventual
adjustment requires a separately reviewed and idempotent financial
correction with documentary evidence and authorization.

`--all-manual` additionally includes manual repayments whose Staff
outbox delivery is marked Completed. This is useful for periodic
reconciliation because delivered does not imply posted or received.
