"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppModal } from "@/components/AppSurface";

export function MarkPaidButton({ runId }: { runId: number }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  function close() {
    if (busy) return;
    setOpen(false);
    setConfirmation("");
  }

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
    setConfirmation("");
    setMessage("Run marked paid.");
    router.refresh();
  }

  return (
    <div className="action-row">
      <button className="button" type="button" onClick={() => setOpen(true)}>Mark paid</button>
      {message ? <span className="muted">{message}</span> : null}
      <AppModal
        open={open}
        eyebrow="Owner confirmation"
        title="Mark payroll run paid"
        description="Paid runs stay locked. Use corrections for later changes."
        onClose={close}
        closeLabel="Close Mark payroll run paid"
        footer={(
          <div className="action-row">
            <button className="button ghost" type="button" disabled={busy} onClick={close}>Cancel</button>
            <button className="button danger" type="button" disabled={busy || confirmation !== "MARK PAID"} onClick={submit}>
              {busy ? "Saving..." : "Confirm paid"}
            </button>
          </div>
        )}
      >
        <div className="form-grid">
          <label>Payment reference<input value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Optional" /></label>
          <label>Type MARK PAID<input autoComplete="off" autoFocus value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="MARK PAID" spellCheck={false} /></label>
        </div>
        {message ? <p className="muted">{message}</p> : null}
      </AppModal>
    </div>
  );
}
