"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppModal } from "./AppSurface";

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

  return (
    <AppModal
      open={open}
      eyebrow="Account reminder"
      title="Change your temporary password"
      description="You can continue using the app now. For account security, change the temporary password when convenient."
      onClose={close}
      closeLabel="Close password reminder"
      footer={<><Link className="button" href="/settings/password" onClick={close}>Change password</Link><button className="button ghost" type="button" onClick={close}>Not now</button></>}
    >
      <p className="muted">This reminder is shown once per session until you dismiss it or open password settings.</p>
    </AppModal>
  );
}
