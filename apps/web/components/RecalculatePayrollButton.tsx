"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function RecalculatePayrollButton({ runId }: { runId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function recalculate() {
    const confirmed = window.confirm(
      "Recalculate this Draft from the latest schedule, attendance, leave, OT, employee settings, and cash-advance data? Saved manual employee adjustments will be preserved."
    );
    if (!confirmed) return;

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

    setMessage(data.message || "Draft recalculated.");
    router.refresh();
  }

  return (
    <div className="inline-action-stack">
      <button className="primary-button" type="button" disabled={busy} onClick={recalculate}>
        {busy ? "Recalculating…" : "Recalculate Draft"}
      </button>
      {message ? <span className="footer-note">{message}</span> : null}
    </div>
  );
}
