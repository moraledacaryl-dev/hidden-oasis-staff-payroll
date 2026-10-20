"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

export function ManualRepaymentForm({ advanceId, balance, employeeName }: { advanceId: number; balance: number; employeeName: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  // Reuse the same request ID after a network failure or unknown response.
  // Changing the form values starts a new request, not a replay.
  const pendingRequest = useRef<{ fingerprint: string; key: string } | null>(null);

  async function submit(formData: FormData) {
    if (busy) return;
    setBusy(true);
    setMessage("");
    const amount = Number(formData.get("amount") || 0);
    if (!Number.isFinite(amount) || amount <= 0 || amount > balance) {
      setBusy(false);
      setMessage(`Enter an amount from ₱0.01 to ₱${balance.toLocaleString("en-PH", { minimumFractionDigits: 2 })}.`);
      return;
    }
    const paymentMethod = String(formData.get("payment_method") || "").trim();
    if (!paymentMethod) {
      setBusy(false);
      setMessage("Select how this repayment was actually received.");
      return;
    }

    const repayment = {
      amount,
      repayment_date: String(formData.get("repayment_date") || ""),
      payment_method: paymentMethod,
      reference: String(formData.get("reference") || "") || null,
      notes: String(formData.get("notes") || "") || null,
    };
    const fingerprint = JSON.stringify({ advanceId, ...repayment });
    if (!pendingRequest.current || pendingRequest.current.fingerprint !== fingerprint) {
      pendingRequest.current = { fingerprint, key: crypto.randomUUID() };
    }

    try {
      const response = await fetch(`/api/cash-advances/${advanceId}/repayments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...repayment, idempotency_key: pendingRequest.current.key }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setMessage(typeof data.detail === "string" ? data.detail : "Repayment was not recorded. Confirm its status before submitting again.");
        return;
      }
      pendingRequest.current = null;
      setOpen(false);
      router.refresh();
    } catch {
      // The server may have committed before the connection failed. Retrying
      // with the same key is safe; never silently submit a second payment.
      setMessage("Could not confirm the result. Retry with the same details to check whether payment was recorded.");
    } finally {
      setBusy(false);
    }
  }

  if (balance <= 0) return <span className="muted">Paid in full</span>;
  if (!open) return <button className="primary-button small" type="button" onClick={() => setOpen(true)}>Record payment</button>;

  return (
    <form action={submit} className="form-grid modal-form">
      <div><strong>Repayment for {employeeName}</strong><p className="muted">Current balance: ₱{balance.toLocaleString("en-PH", { minimumFractionDigits: 2 })}</p></div>
      <label>Amount received<input name="amount" type="number" min="0.01" max={balance} step="0.01" defaultValue={balance} required /></label>
      <label>Date received<input name="repayment_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></label>
      <label>Payment method<select name="payment_method" defaultValue="" required><option value="" disabled>Select actual method</option><option>Cash</option><option>GCash</option><option>Bank transfer</option><option>Maya</option><option>Other</option></select></label>
      <label>Reference / receipt<input name="reference" placeholder="Optional receipt or transfer reference" /></label>
      <label>Notes<input name="notes" placeholder="Optional note" /></label>
      <div className="badge-row"><button className="primary-button" type="submit" disabled={busy}>{busy ? "Recording…" : "Confirm repayment"}</button><button className="button ghost" type="button" disabled={busy} onClick={() => { pendingRequest.current = null; setOpen(false); }}>Cancel</button></div>
      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
