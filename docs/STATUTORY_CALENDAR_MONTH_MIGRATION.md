# Statutory calendar-month contribution invariant

Payroll cutoffs and statutory contribution months are separate concepts.

A cutoff that crosses month-end must be segmented by earning date before a monthly statutory basis is calculated. For example, the earning period `2026-08-31` through `2026-09-14` has two statutory segments:

- August: `2026-08-31` through `2026-08-31`
- September: `2026-09-01` through `2026-09-14`

Neither `period_start` nor `period_end` may be used as a single month anchor for the whole cutoff.

## Migration requirements

1. Same-month payrolls retain their existing results.
2. SSS month-to-date remuneration is accumulated independently for each calendar month represented by the cutoff.
3. PhilHealth and Pag-IBIG monthly obligations are allocated without treating a cross-month cutoff as the closing cutoff of the starting month.
4. Benefits-disabled employees remain zero.
5. All post-compute corrections (split shifts, night differential, holiday/paid-leave and money-boundary recomputation) must call the same statutory implementation.
6. Historical payroll snapshots are immutable. In particular, this migration must not update existing `payroll_runs` or `payroll_items`; corrections to an already paid payroll use the payroll revision/adjustment workflow.
7. Prior-contribution lookup must not double-count a superseded payroll revision and its replacement.

`core.stat​utory_periods.calendar_month_segments` (without the zero-width character in normal source spelling: `core.statutory_periods.calendar_month_segments`) is the boundary primitive for this migration.
