# Prospective Cash Advance Release → Accounting Review

## Scope and boundary

This workflow is for **new Staff cash advances created after the release-confirmation upgrade**. Existing Staff advances and historical repayments are intentionally excluded; do not infer a payment from approval, a paid balance, a date match, or a previous delivery attempt.

1. Creating an advance records a **Pending** request with `release_confirmation_required=1`.
2. Approval moves the record to **Active**. It is **not a cash-out** and does **not** enqueue a release event.
3. An authorized Owner/Payroll user must explicitly confirm that the funds were **actually issued**, supplying the actual release date, resort cash drawer/GCash/bank method, digital transfer reference where applicable, and a confirmation checkbox.
4. One SQLite transaction saves release evidence, appends the lifecycle audit event, creates a linked cash-drawer movement for drawer releases, and enqueues the idempotent `cash_advance.released` Accounting review event. Outbox failure rolls back the entire release. Network retries with identical evidence return `already_recorded=true`.
5. A new unissued advance cannot receive a manual repayment or an automatic payroll deduction. This constraint does not retroactively change historical advances.
6. An issued advance cannot be cancelled using the undisbursed-cancellation endpoint. Corrections/reversals require explicit, separately audited treatment.

## Financial boundaries

The `cash_advance.released` event is **review intake**, not authorization to post Accounting journals or proof of a bank/GCash statement. The receiver must verify cash custody, receiving account, source identity, and Employee Advances Receivable mapping. Expected accounting nature is **Dr Employee Advances Receivable / Cr actual cash-or-wallet account** (not wage expense).

The outbox's transport status is *not* downstream journal acceptance or proof the funds changed hands. Cash drawer movement status is *For Reconciliation*, not a second expense. No historical backfills or automatic Accounting ledger writes occur in this change.

## Known historical exceptions

Five previously recorded manual repayments, ₱10,500 total, lack Staff Accounting outbox events. The known #30 / advance #26 / ₱3,000 repayment concerns Benjie Galarrita and carries a user-supplied GCash reference. Neither event emission nor posting is performed on those legacy records by this new workflow.

## Verification

- `python -m unittest tests.test_confirmed_cash_advance_release -v`
- `python -m unittest discover -v`
- `npm --prefix apps/web run lint && npm --prefix apps/web run typecheck && npm --prefix apps/web run build`
- Browser smoke screenshots at mobile, tablet and desktop dimensions.
