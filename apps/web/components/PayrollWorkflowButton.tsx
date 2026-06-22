"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Action = "submit-review" | "approve";

export function PayrollWorkflowButton({ runId, action }: { runId: number; action: Action }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const isApprove = action === "approve";
  const label = isApprove ? "Approve payroll" : "Submit for owner review";

  async function submit() {
    const confirmed = window.confirm(
      isApprove
        ? "Approve this payroll run? The figures will be locked for release."
        : "Submit this Draft for owner review? Editing will stop until it is returned or revised."
    );
    if (!confirmed) return;

    setBusy(true);
    setMessage("");
    const response = await fetch("/api/payroll/workflow", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, action }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);

    if (!response.ok || !data.ok) {
      const detail = data.detail;
      setMessage(typeof detail === "string" ? detail : data.message || "Payroll status was not changed.");
      return;
    }

    setMessage(isApprove ? "Payroll approved." : "Submitted for owner review.");
    router.refresh();
  }

  return (
    <div className="action-row">
      <button className={isApprove ? "primary-button" : "button"} type="button" disabled={busy} onClick={submit}>
        {busy ? "Saving..." : label}
      </button>
      {message ? <span className="muted">{message}</span> : null}
    </div>
  );
}
