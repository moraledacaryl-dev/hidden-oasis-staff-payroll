"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function PayrollDraftButton({ periodStart, periodEnd, payoutDate }: { periodStart: string; periodEnd: string; payoutDate: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function createDraft() {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/payroll/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ period_start: periodStart, period_end: periodEnd, payout_date: payoutDate, run_label: "Semi-monthly" }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Draft was not created. Check blockers or duplicate run.");
      return;
    }
    setMessage("Draft saved. Payroll is not released.");
    router.refresh();
  }

  return (
    <div className="decision-stack wide-action">
      <button className="mini-button" disabled={busy} onClick={createDraft} type="button">{busy ? "Saving draft..." : "Create payroll draft"}</button>
      <span className="muted">Release remains disabled.</span>
      {message ? <span className="inline-error">{message}</span> : null}
    </div>
  );
}
