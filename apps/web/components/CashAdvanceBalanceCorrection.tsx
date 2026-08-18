"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

function peso(value: number): string {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(Number(value || 0));
}

export function CashAdvanceBalanceCorrection({
  advanceId,
  employeeName,
  currentBasis,
  totalRepaid,
}: {
  advanceId: number;
  employeeName: string;
  currentBasis: number;
  totalRepaid: number;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [correctedBasis, setCorrectedBasis] = useState(Number(currentBasis || 0));
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  const basis = Math.max(0, Number(correctedBasis || 0));
  const repaid = Math.max(0, Number(totalRepaid || 0));
  const projectedBalance = Math.max(0, basis - repaid);
  const projectedCredit = Math.max(0, repaid - basis);
  const changed = Math.abs(basis - Number(currentBasis || 0)) >= 0.005;

  function close() {
    setOpen(false);
    setMessage("");
    setCorrectedBasis(Number(currentBasis || 0));
    setReason("");
    setReference("");
    setConfirmed(false);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!changed) {
      setMessage("Enter a corrected balance basis different from the current basis.");
      return;
    }
    if (basis <= 0) {
      setMessage("Corrected balance basis must be greater than zero.");
      return;
    }
    if (!reason.trim()) {
      setMessage("Enter a correction reason.");
      return;
    }
    if (!confirmed) {
      setMessage("Confirm that you reviewed the correction consequences.");
      return;
    }

    setBusy(true);
    setMessage("");
    const response = await fetch("/api/cash-advances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "correct_amount",
        cash_advance_id: advanceId,
        corrected_amount: basis,
        correction_reason: reason.trim(),
        reference: reference.trim() || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || "Balance correction was not saved.");
      return;
    }
    close();
    router.refresh();
  }

  if (!open) {
    return <button className="button small ghost" type="button" onClick={() => setOpen(true)}>Correct balance basis</button>;
  }

  return (
    <section className="cash-basis-correction" aria-label={`Correct cash advance balance basis for ${employeeName}`}>
      <div className="cash-basis-header">
        <div>
          <span>Owner correction</span>
          <h3>Correct balance basis</h3>
          <p>This action changes the financial basis only. It does not run the normal cash-advance edit flow.</p>
        </div>
        <button className="button ghost" type="button" onClick={close}>Close</button>
      </div>

      <form onSubmit={submit}>
        <div className="cash-basis-stats">
          <div><span>Previous basis</span><strong>{peso(currentBasis)}</strong></div>
          <div><span>Repayments applied</span><strong>{peso(repaid)}</strong></div>
          <div><span>Projected remaining</span><strong>{peso(projectedBalance)}</strong></div>
          <div><span>Employee credit</span><strong>{peso(projectedCredit)}</strong></div>
        </div>

        <label className="cash-basis-field">
          <span>Corrected basis</span>
          <input type="number" min="0.01" step="0.01" value={correctedBasis} onChange={(event) => { setCorrectedBasis(Number(event.target.value || 0)); setConfirmed(false); }} required />
        </label>
        <label className="cash-basis-field">
          <span>Correction reason</span>
          <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why the recorded balance basis was incorrect" required />
        </label>
        <label className="cash-basis-field">
          <span>Reference</span>
          <input value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Optional voucher or accounting reference" />
        </label>
        <label className="cash-basis-confirm">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          <span>I reviewed the new remaining balance and any employee credit.</span>
        </label>

        {projectedCredit > 0 ? <p className="cash-basis-warning">This correction creates an employee credit of {peso(projectedCredit)} that must be settled separately.</p> : null}
        {message ? <p className="cash-basis-error">{message}</p> : null}
        <div className="cash-basis-actions">
          <button className="button ghost" type="button" onClick={close}>Cancel</button>
          <button className="primary-button" type="submit" disabled={busy || !changed}>{busy ? "Saving…" : "Confirm correction"}</button>
        </div>
      </form>

      <style jsx>{`
        .cash-basis-correction{display:grid;gap:14px;width:100%;padding:16px;border:1px solid #e9c982;border-radius:8px;background:var(--warning-soft)}
        .cash-basis-header{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.cash-basis-header span{color:var(--warning);font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em}.cash-basis-header h3{margin:2px 0 4px}.cash-basis-header p{margin:0;color:var(--muted);font-size:.8rem}
        form{display:grid;gap:12px}.cash-basis-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.cash-basis-stats div{display:grid;gap:4px;padding:11px;border-radius:6px;background:rgba(255,255,255,.72)}.cash-basis-stats span,.cash-basis-field>span{color:var(--muted);font-size:.67rem;font-weight:800;text-transform:uppercase;letter-spacing:.055em}.cash-basis-field{display:grid;gap:6px}.cash-basis-field input{width:100%}.cash-basis-confirm{display:flex;align-items:flex-start;gap:8px;font-size:.82rem}.cash-basis-confirm input{margin-top:2px}.cash-basis-warning,.cash-basis-error{margin:0;padding:10px 12px;border-radius:6px;background:rgba(255,255,255,.72);font-size:.8rem;font-weight:750}.cash-basis-warning{color:var(--danger)}.cash-basis-error{color:var(--danger)}.cash-basis-actions{display:flex;justify-content:flex-end;gap:8px}
        @media(max-width:720px){.cash-basis-header{display:grid}.cash-basis-stats{grid-template-columns:1fr 1fr}.cash-basis-actions button{flex:1}}
      `}</style>
    </section>
  );
}
