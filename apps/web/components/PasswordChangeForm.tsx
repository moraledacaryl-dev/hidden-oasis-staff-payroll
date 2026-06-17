"use client";

import { useState } from "react";

export function PasswordChangeForm() {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const newPassword = String(formData.get("new_password") || "");
    const confirm = String(formData.get("confirm_password") || "");
    if (newPassword.length < 8) {
      setBusy(false);
      setMessage("Use at least 8 characters.");
      return;
    }
    if (newPassword !== confirm) {
      setBusy(false);
      setMessage("New passwords do not match.");
      return;
    }
    const response = await fetch("/api/settings/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: String(formData.get("current_password") || ""),
        new_password: newPassword,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Password was not changed.");
      return;
    }
    setMessage("Password changed.");
  }

  return (
    <form action={submit} className="form-grid">
      <label>Current password<input name="current_password" type="password" required autoComplete="current-password" /></label>
      <label>New password<input name="new_password" type="password" required minLength={8} autoComplete="new-password" /></label>
      <label>Confirm new password<input name="confirm_password" type="password" required minLength={8} autoComplete="new-password" /></label>
      <button className="primary-button" type="submit" disabled={busy}>{busy ? "Changing..." : "Change password"}</button>
      {message ? <p className="muted">{message}</p> : null}
    </form>
  );
}
