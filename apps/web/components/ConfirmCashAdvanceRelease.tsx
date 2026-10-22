"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppDrawer } from "@/components/AppSurface";
import { clientRequest } from "@/lib/client-request";

export function ConfirmCashAdvanceRelease({
  advanceId, employeeName, amount, advanceDate,
}: { advanceId: number; employeeName: string; amount: number; advanceDate: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [method, setMethod] = useState("Cash Drawer");

  async function confirm(formData: FormData) {
    if (busy) return;
    setBusy(true);
    setError("");
    const payload = {
      action: "release",
      cash_advance_id: advanceId,
      release_date: String(formData.get("release_date") || ""),
      release_method: String(formData.get("release_method") || ""),
      reference: String(formData.get("reference") || "").trim() || null,
      confirmed_received: formData.get("confirmed_received") === "on",
    };
    try {
      const response = await clientRequest("/api/cash-advances", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(typeof data.detail === "string" ? data.detail : "Could not confirm release.");
        return;
      }
      setOpen(false);
      router.refresh();
    } catch {
      setError("Could not verify the result. Refresh this page before submitting again; never record a second release.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <button className="button secondary" type="button" onClick={() => { setError(""); setOpen(true); }}>Confirm funds issued</button>
    <AppDrawer
      open={open}
      eyebrow="Cash advance release"
      title={`Confirm release to ${employeeName}`}
      description={`Advance #${advanceId} · ₱${amount.toLocaleString("en-PH", { minimumFractionDigits: 2 })}. Approval alone does not mean funds were disbursed.`}
      onClose={() => { if (!busy) setOpen(false); }}
    >
      <form action={confirm} className="form-grid">
        <label>Actual release date
          <input type="date" name="release_date" min={advanceDate.slice(0, 10)} required aria-describedby="advance-release-date-help" />
        </label>
        <p className="cash-release-date-help" id="advance-release-date-help">
          Record the date funds were actually handed over, not the approval date. It cannot precede the advance date.
        </p>
        <label>Funds issued from
          <select name="release_method" value={method} onChange={(event) => setMethod(event.target.value)} required>
            <option value="Cash Drawer">Resort cash drawer</option>
            <option value="GCash">Resort GCash</option>
            <option value="Bank Transfer">Resort bank transfer</option>
          </select>
        </label>
        <label>Voucher / transfer reference
          <input name="reference" maxLength={160} required={method !== "Cash Drawer"} placeholder={method === "Cash Drawer" ? "Optional cash voucher" : "Required transfer reference"} />
        </label>
        <label className="cash-release-attestation">
          <input type="checkbox" name="confirmed_received" required />
          <span>I confirm the employee was actually given these funds. This will create a Staff Accounting review handoff, not post a journal automatically.</span>
        </label>
        {error ? <p role="alert" className="danger-text">{error}</p> : null}
        <div className="badge-row">
          <button type="submit" className="primary-button" disabled={busy}>{busy ? "Recording…" : "Confirm actual disbursement"}</button>
          <button type="button" className="button secondary" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
        </div>
      </form>
    </AppDrawer>
  </>;
}
