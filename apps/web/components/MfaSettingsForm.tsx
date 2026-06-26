"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Setup = { secret: string; otpauth_uri: string };

export function MfaSettingsForm({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(body: Record<string, unknown>) {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/settings/security", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage(data.detail || "Security update failed.");
      return null;
    }
    return data;
  }

  async function beginSetup() {
    const data = await send({ action: "setup" });
    if (data) setSetup({ secret: data.secret, otpauth_uri: data.otpauth_uri });
  }

  async function confirm() {
    const data = await send({ action: "confirm", code });
    if (data) {
      setMessage(data.message);
      window.setTimeout(() => {
        router.push("/login");
        router.refresh();
      }, 500);
    }
  }

  async function disable() {
    const data = await send({ action: "disable", code, password });
    if (data) {
      setMessage(data.message);
      window.setTimeout(() => {
        router.push("/login");
        router.refresh();
      }, 500);
    }
  }

  if (enabled) {
    return (
      <div className="form-grid">
        <label>Current password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <label>Authenticator code<input inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label>
        <button className="button danger" type="button" disabled={busy || !password || code.length !== 6} onClick={disable}>Disable authenticator</button>
        {message ? <p className="muted">{message}</p> : null}
      </div>
    );
  }

  return (
    <div className="grid">
      {!setup ? <button className="button" type="button" disabled={busy} onClick={beginSetup}>Set up authenticator</button> : null}
      {setup ? (
        <>
          <div className="copy-box"><strong>{setup.secret}</strong></div>
          <a className="primary-link" href={setup.otpauth_uri}>Open authenticator app</a>
          <div className="form-grid">
            <label>Authenticator code<input inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label>
            <button className="button" type="button" disabled={busy || code.length !== 6} onClick={confirm}>Confirm</button>
          </div>
        </>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}
