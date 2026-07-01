"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function ImpersonationBanner({
  targetName,
  targetRole,
}: {
  targetName: string;
  targetRole: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function stop() {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/session/impersonate/stop", { method: "POST" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      setMessage(data.message || "Could not restore the Owner session.");
      setBusy(false);
      return;
    }
    router.push("/settings/users");
    router.refresh();
  }

  return (
    <div className="impersonation-banner" data-impersonation-banner>
      <div>
        <strong>Viewing as {targetName}</strong>
        <span>{targetRole}</span>
      </div>
      <button className="button small" disabled={busy} onClick={stop} type="button">
        {busy ? "Returning..." : "Return to Owner"}
      </button>
      {message ? <span className="error-text">{message}</span> : null}
    </div>
  );
}
