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

  const baseButton = {
    minHeight: 32,
    padding: "7px 12px",
    borderRadius: 7,
    fontWeight: 850,
    fontSize: "0.8rem",
    lineHeight: 1,
    flex: "0 0 auto",
  } as const;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      <button
        disabled={Boolean(busy)}
        onClick={() => decide("Approved")}
        style={{ ...baseButton, border: "1px solid var(--accent)", background: "var(--accent)", color: "#fff" }}
        type="button"
      >
        {busy === "Approved" ? "Approving..." : "Approve"}
      </button>
      <button
        disabled={Boolean(busy)}
        onClick={() => decide("Needs Correction")}
        style={{ ...baseButton, border: "1px solid var(--line-strong)", background: "#fff", color: "var(--ink)" }}
        type="button"
      >
        Fix
      </button>
      <button
        disabled={Boolean(busy)}
        onClick={() => decide("Rejected")}
        style={{ ...baseButton, border: "1px solid var(--danger)", background: "var(--danger)", color: "#fff" }}
        type="button"
      >
        Reject
      </button>
      {error ? <span className="inline-error">{error}</span> : null}
    </div>
  );
}
