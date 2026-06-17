"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { RoleKey } from "@/lib/types";

export function PayrollLifecycleButtons({ runId, status, role = "owner" }: { runId: number; status: string; role?: RoleKey }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function submit(action: "lock" | "approve" | "reopen") {
    const reason = action === "reopen" ? window.prompt("Reason for reopening this payroll run:") : "";
    if (action === "reopen" && (!reason || reason.trim().length < 3)) return;
    setBusy(action);
    setMessage(null);
    const response = await fetch("/api/payroll/lifecycle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, action, reason }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Action failed.");
      setBusy(null);
      return;
    }
    setMessage("Saved.");
    setBusy(null);
    router.refresh();
  }

  return (
    <div className="action-row">
      {status === "Draft" ? <button className="button small" disabled={!!busy} onClick={() => submit("lock")}>{busy === "lock" ? "Locking..." : "Lock"}</button> : null}
      {role === "owner" && status === "For Owner Review" ? <button className="button small" disabled={!!busy} onClick={() => submit("approve")}>{busy === "approve" ? "Approving..." : "Approve"}</button> : null}
      {role === "owner" && (status === "For Owner Review" || status === "Approved") ? <button className="button small ghost" disabled={!!busy} onClick={() => submit("reopen")}>{busy === "reopen" ? "Reopening..." : "Reopen"}</button> : null}
      {message ? <span className="muted">{message}</span> : null}
    </div>
  );
}
