"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmActionModal } from "@/components/ConfirmActionModal";

export function RecalculatePayrollButton({ runId }: { runId: number }) {
  const router = useRouter();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

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

  return (
    <div className="inline-action-stack">
      <button className="primary-button" type="button" disabled={busy} onClick={() => setConfirmOpen(true)}>
        {busy ? "Recalculating…" : "Recalculate Draft"}
      </button>
      {message ? <span className="footer-note">{message}</span> : null}
      <ConfirmActionModal
        open={confirmOpen}
        title="Recalculate payroll draft?"
        description="This rebuilds the Draft from the latest schedule, attendance, leave, OT, employee settings, and cash-advance data. Saved manual employee adjustments will be preserved."
        confirmLabel="Recalculate Draft"
        busy={busy}
        onClose={() => setConfirmOpen(false)}
        onConfirm={recalculate}
      />
    </div>
  );
}
