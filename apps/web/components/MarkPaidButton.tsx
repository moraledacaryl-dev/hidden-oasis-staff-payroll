"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function MarkPaidButton({ runId }: { runId: number }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit() {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/payroll/mark-paid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, confirmation, reference }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Could not mark paid.");
      return;
    }
    setOpen(false);
    setMessage("Run marked paid.");
    router.refresh();
  }

  return (
    <div className="action-row">
      <button className="button" type="button" onClick={() => setOpen(true)}>Mark paid</button>
      {message ? <span className="muted">{message}</span> : null}
      {open ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-panel compact-modal">
            <div className="panel-title">
              <div>
                <span className="eyebrow">Owner confirmation</span>
                <h2>Mark payroll run paid</h2>
              </div>
              <button className="button small ghost" type="button" onClick={() => setOpen(false)}>Close</button>
            </div>
            <p className="muted">Paid runs should not be silently edited. Later changes should be handled through payroll corrections so the audit trail stays intact.</p>
            <div className="form-grid" style={{ marginTop: 12 }}>
              <label>Payment reference<input value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Optional" /></label>
              <label>Type MARK PAID<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="MARK PAID" /></label>
            </div>
            <div className="action-row" style={{ marginTop: 12 }}>
              <button className="primary-button" type="button" disabled={busy || confirmation !== "MARK PAID"} onClick={submit}>{busy ? "Saving..." : "Confirm paid"}</button>
              {message ? <span className="muted">{message}</span> : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
