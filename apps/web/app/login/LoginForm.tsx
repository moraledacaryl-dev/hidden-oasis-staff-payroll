"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LogIn } from "lucide-react";
import { defaultPathForRole } from "@/lib/session-client";
import type { RoleKey } from "@/lib/types";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [displayName, setDisplayName] = useState("");
  const [secret, setSecret] = useState("");
  const [otp, setOtp] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = useMemo(() => searchParams.get("next"), [searchParams]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const response = await fetch("/api/session/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: displayName,
        password: secret,
        otp: otp.trim() || undefined,
      }),
    });
    if (!response.ok) {
      const failed = await response.json().catch(() => ({}));
      if (response.status === 428) {
        setMfaRequired(true);
        setOtp("");
        setError("Enter the 6-digit code from your authenticator app.");
      } else {
        setError(failed.message || "Sign in failed.");
      }
      setBusy(false);
      return;
    }
    const data = await response.json();
    const actualRole = (data.user?.role_key || "staff") as RoleKey;
    const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
    const destination = safeNext || defaultPathForRole(actualRole);
    router.push(destination);
    router.refresh();
  }

  return (
    <form className="login-card" onSubmit={submit}>
      <div className="brand-mark">HO</div>
      <div className="grid"><span className="eyebrow">Staff Payroll</span><h1>Sign in</h1></div>
      <div className="field"><label htmlFor="displayName">Display name</label><input id="displayName" value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="username" required /></div>
      <div className="field"><label htmlFor="secret">Password</label><input id="secret" type="password" value={secret} onChange={(event) => setSecret(event.target.value)} autoComplete="current-password" required /></div>
      {mfaRequired ? (
        <div className="field">
          <label htmlFor="otp">Authenticator code</label>
          <input
            id="otp"
            value={otp}
            onChange={(event) =>
              setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))
            }
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="123456"
            autoFocus
            required
          />
        </div>
      ) : null}
      {error ? <p className="badge danger" role="alert">{error}</p> : null}
      <button className="primary-button" type="submit" disabled={busy}>
        <LogIn aria-hidden="true" size={17} />
        {busy
          ? "Signing in..."
          : mfaRequired
            ? "Verify and sign in"
            : "Sign in"}
      </button>
    </form>
  );
}
