"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function AttendanceDecisionButtons({ timeLogId, detectedOtHours }: { timeLogId: number; detectedOtHours: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function decide(decision: "Approved" | "Rejected" | "Needs Correction") {
    setBusy(decision);
    setError("");
    const response = await fetch("/api/attendance/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        time_log_id: timeLogId,
        decision,
        approved_ot_hours: decision === "Approved" ? detectedOtHours : 0,
        reason: `General Manager selected ${decision}.`,
      }),
    });
    setBusy(null);
    if (!response.ok) {
      setError("Action failed. Refresh and try again.");
      return;
    }
    router.refresh();
  }

  return (
    <div className="decision-stack">
      <button className="mini-button" disabled={Boolean(busy)} onClick={() => decide("Approved")} type="button">{busy === "Approved" ? "Approving..." : "Approve"}</button>
      <button className="mini-button muted-button" disabled={Boolean(busy)} onClick={() => decide("Needs Correction")} type="button">Fix</button>
      <button className="mini-button danger-button" disabled={Boolean(busy)} onClick={() => decide("Rejected")} type="button">Reject</button>
      {error ? <span className="inline-error">{error}</span> : null}
    </div>
  );
}
