"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export function PasswordReminderDialog({ userId }: { userId: number }) {
  const storageKey = `hidden-oasis-password-reminder-dismissed:${userId}`;
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try {
      setOpen(sessionStorage.getItem(storageKey) !== "1");
    } catch {
      setOpen(true);
    }
  }, [storageKey]);

  function close() {
    try {
      sessionStorage.setItem(storageKey, "1");
    } catch {
      // Ignore storage failures; the close action should still work for this render.
    }
    setOpen(false);
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="password-reminder-title">
      <section className="modal-panel compact-modal password-reminder-modal">
        <div className="panel-title">
          <div>
            <span className="eyebrow">Account reminder</span>
            <h2 id="password-reminder-title">Change your temporary password</h2>
          </div>
          <button className="button ghost" type="button" onClick={close}>Close</button>
        </div>
        <p className="muted">You can continue using the app now. For account security, change the temporary password when convenient.</p>
        <div className="action-row" style={{ marginTop: 14 }}>
          <Link className="button" href="/settings/password" onClick={close}>Change password</Link>
          <button className="button ghost" type="button" onClick={close}>Not now</button>
        </div>
      </section>
    </div>
  );
}
