"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { mondayOfWeek } from "@/lib/period";

export function AttendanceDecisionButtons({
  timeLogId,
  detectedOtHours,
  workDate,
  employeeId,
}: {
  timeLogId: number;
  detectedOtHours: number;
  workDate?: string;
  employeeId?: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function approve() {
    setBusy("Approved");
    setError("");
    const response = await fetch("/api/attendance/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        time_log_id: timeLogId,
        decision: "Approved",
        approved_ot_hours: detectedOtHours,
        reason: "General Manager approved this review item.",
      }),
    });
    setBusy(null);
    if (!response.ok) {
      setError("Action failed. Refresh and try again.");
      return;
    }
    router.refresh();
  }

  function openSchedule() {
    if (!workDate) {
      router.push("/schedule");
      return;
    }
    const params = new URLSearchParams();
    params.set("week_start", mondayOfWeek(workDate));
    if (employeeId) params.set("employee_id", String(employeeId));
    router.push(`/schedule?${params.toString()}`);
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
        onClick={approve}
        style={{ ...baseButton, border: "1px solid var(--accent)", background: "var(--accent)", color: "#fff" }}
        type="button"
      >
        {busy === "Approved" ? "Approving..." : "Approve"}
      </button>
      <button
        disabled={Boolean(busy)}
        onClick={openSchedule}
        style={{ ...baseButton, border: "1px solid var(--line-strong)", background: "#fff", color: "var(--ink)" }}
        type="button"
      >
        Fix
      </button>
      {error ? <span className="inline-error">{error}</span> : null}
    </div>
  );
}
