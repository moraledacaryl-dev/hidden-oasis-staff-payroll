"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmActionModal } from "@/components/ConfirmActionModal";

export function RecalculatePayrollButton({ runId }: { runId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  async function recalculate() {
    setBusy(true);
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/recalculate`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(false);

    if (!response.ok || !data.ok) {
      const detail = data.detail;
      if (typeof detail === "string") setMessage(detail);
      else if (detail?.message) setMessage(detail.message);
      else setMessage("Draft could not be recalculated.");
      return;
    }

    setConfirmOpen(false);
    setMessage(data.message || "Draft recalculated.");
    router.refresh();
  }

  async function deleteDraft() {
    setBusy(true);
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/delete-draft`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(false);

    if (!response.ok || !data.ok) {
      const detail = data.detail;
      if (typeof detail === "string") setMessage(detail);
      else if (detail?.message) setMessage(detail.message);
      else setMessage("Draft could not be deleted.");
      return;
    }

    setDeleteOpen(false);
    router.push("/payroll");
    router.refresh();
  }

  return (
    <>
      <div className="inline-action-stack">
        <div className="action-row">
          <button className="primary-button" type="button" disabled={busy} onClick={() => setConfirmOpen(true)}>
            {busy ? "Working…" : "Recalculate Draft"}
          </button>
          <button className="button ghost" type="button" disabled={busy} onClick={() => setDeleteOpen(true)}>
            Delete Draft
          </button>
        </div>
        {message ? <span className="footer-note">{message}</span> : null}
      </div>

      <ConfirmActionModal
        open={confirmOpen}
        title="Recalculate payroll draft"
        description="Recalculate this Draft from the latest schedule, attendance, leave, OT, employee settings, and cash-advance data. Saved manual employee adjustments will be preserved."
        confirmLabel="Recalculate Draft"
        busy={busy}
        onClose={() => setConfirmOpen(false)}
        onConfirm={recalculate}
      />

      <ConfirmActionModal
        open={deleteOpen}
        title="Delete payroll draft"
        description="Delete this Draft payroll run and its draft-only calculations and adjustments. Approved, paid, released, or locked payrolls can never be deleted. After deletion you can create a new Draft with the correct dates."
        confirmLabel="Delete Draft"
        busy={busy}
        onClose={() => setDeleteOpen(false)}
        onConfirm={deleteDraft}
      />
    </>
  );
}
