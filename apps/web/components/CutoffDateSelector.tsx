"use client";

export function CutoffDateSelector({
  periodStart,
  periodEnd,
  payoutDate,
  latestAllowedEnd,
}: {
  periodStart: string;
  periodEnd: string;
  payoutDate: string;
  latestAllowedEnd: string;
}) {
  return (
    <form className="cutoff-form" method="get">
      <span className="cutoff-toolbar-label">Cutoff</span>
      <div className="field cutoff-field">
        <label htmlFor="cutoff-start">From</label>
        <input
          data-cutoff-start="true"
          data-payroll-cutoff-start="true"
          id="cutoff-start"
          max={latestAllowedEnd}
          name="start"
          type="date"
          defaultValue={periodStart}
        />
      </div>
      <div className="field cutoff-field">
        <label htmlFor="cutoff-end">To</label>
        <input
          data-cutoff-end="true"
          data-payroll-cutoff-end="true"
          id="cutoff-end"
          max={latestAllowedEnd}
          name="end"
          type="date"
          defaultValue={periodEnd}
        />
      </div>
      <div className="field cutoff-field">
        <label htmlFor="payout-date">Payment date</label>
        <input
          data-payroll-payout-date="true"
          id="payout-date"
          min={periodEnd}
          name="payout"
          type="date"
          defaultValue={payoutDate}
        />
      </div>
      <button className="primary-button" type="submit">View</button>
    </form>
  );
}
