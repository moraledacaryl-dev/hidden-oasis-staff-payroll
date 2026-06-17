"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = {
  currentWeekStart: string;
  previousWeekStart: string;
};

export function ScheduleCopyWeekForm({ currentWeekStart, previousWeekStart }: Props) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function copyPreviousWeek() {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/schedule/copy-week", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_week_start: previousWeekStart, to_week_start: currentWeekStart }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || data.message || "Week copy failed.");
      return;
    }
    setMessage(`Copied ${data.copied || 0} planned shift(s).`);
    router.refresh();
  }

  return (
    <div className="action-row">
      <button className="primary-link" type="button" disabled={busy} onClick={copyPreviousWeek}>
        {busy ? "Copying…" : "Copy previous week"}
      </button>
      {message ? <span className="muted">{message}</span> : null}
    </div>
  );
}
