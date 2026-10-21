# Historical manual repayment reconciliation: Staff ledger context

The October 2026 production audits identified **five active manual repayments
totalling ₱10,500** for which no Staff Accounting outbox event or exact
Accounting source-identity match was found.

Accounting's nearby-date candidates were subsequently classified as:
- #940: Room direct booking revenue (a possible date/amount lead for both
  Staff #42 and Staff #43)
- #1125: Room direct booking revenue (Staff #30 lead)
- #1538 and #1539: Guest damage charges (Staff #29 leads)

These are not safe repayment source matches. No Accounting journal, Money In
entry, historical repayment, or cash balance should be changed based on those
amount coincidences.

## Next diagnostic: Staff advance ledger (read only)

Run directly from an audited GitHub commit on the server, without deploying
a Staff application release:

```bash
source /etc/hiddenoasis/staff-payroll.env
python3 scripts/audit_manual_repayment_ledger_context.py \
  --db "$STAFF_PAYROLL_DB_PATH" --limit 30
```

The audit opens SQLite with `mode=ro` and `PRAGMA query_only=ON`.
It mirrors the current Staff balance engine's opening balance fallback and
counts active Manual repayments plus payroll-linked deductions associated with
`Paid`, `Locked`, or `Released` payroll runs. Draft payroll deductions are
**not** treated as settled. Inactive/reversed repayments are shown separately.

The result reports:
- Cash advance ID, original amount, ledger opening balance and stored balances
- Active manual repayment totals, confirmed and unconfirmed payroll deductions
- Arithmetic discrepancies and potential over-application
- Same-day/same-amount repayments against **different** cash advances
- Presence (never the value) of receipt references

The ledger opening amount may reflect historical repayments before this ledger
was introduced. It does not necessarily equal the originally released amount.
A computed balance agreeing with the stored balance verifies arithmetic only,
**not receipt of cash**. The `cash_receipt_independently_verified` flag is
always false until external records are actually reconciled.

## Operator follow-up

For Staff repayments #15, #29, #30, #42 and #43:

1. Independently verify the original Staff repayment source and cash advance,
   including whether another payroll run deducted the same amount.
2. Locate the physical receipt, cash-book entry or deposit and check against
   receiving-account statements. The lack of matching Accounting source IDs
   does not prove the funds were never received.
3. Determine the actual receiving method for Staff #30 (₱3,000, `Other`).
4. Keep #42 and #43 distinct unless there is evidence both were part of an
   independently documented consolidated cash deposit.
5. Only after documentary proof, design a separately reviewed and idempotent
   correction; do **not** bulk replay the five missing outbox events.

Never paste employee names, payroll identifiers, payment receipt numbers,
private notes, API keys, or environment file contents into issue/PR logs.
