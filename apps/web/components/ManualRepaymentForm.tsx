"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function ManualRepaymentForm({ advanceId, balance, employeeName }: { advanceId: number; balance: number; employeeName: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const amount = Number(formData.get("amount") || 0);
    if (amount <= 0 || amount > balance) {
      setBusy(false);
      setMessage(`Enter an amount from ₱0.01 to ₱${balance.toLocaleString("en-PH", { minimumFractionDigits: 2 })}.`);
      return;
    }
    const response = await fetch(`/api/cash-advances/${advanceId}/repayments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount,
        repayment_date: String(formData.get("repayment_date") || ""),
        payment_method: String(formData.get("payment_method") || "Cash"),
        reference: String(formData.get("reference") || "") || null,
        notes: String(formData.get("notes") || "") || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Repayment was not recorded.");
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (balance <= 0) return <span className="muted">Paid in full</span>;
  if (!open) return <button className="primary-button small" type="button" onClick={() => setOpen(true)}>Record payment</button>;

  return (
    <form action={submit} className="form-grid modal-form">
      <div><strong>Repayment for {employeeName}</strong><p className="muted">Current balance: ₱{balance.toLocaleString("en-PH", { minimumFractionDigits: 2 })}</p></div>
      <label>Amount received<input name="amount" type="number" min="0.01" max={balance} step="0.01" defaultValue={balance} required /></label>
      <label>Date received<input name="repayment_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></label>
      <label>Payment method<select name="payment_method" defaultValue="Cash"><option>Cash</option><option>Bank transfer</option><option>Other</option></select></label>
      <label>Reference / receipt<input name="reference" placeholder="Optional receipt or transfer reference" /></label>
      <label>Notes<input name="notes" placeholder="Optional note" /></label>
      <div className="badge-row"><button className="primary-button" type="submit" disabled={busy}>{busy ? "Recording…" : "Confirm repayment"}</button><button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button></div>
      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
