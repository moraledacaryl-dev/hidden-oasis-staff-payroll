"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { defaultPathForRole } from "@/lib/session-client";
import type { RoleKey } from "@/lib/types";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [displayName, setDisplayName] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const next = useMemo(() => searchParams.get("next"), [searchParams]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/session/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName, password: secret }),
    });
    if (!response.ok) {
      setError("Invalid user or password.");
      return;
    }
    const data = await response.json();
    const actualRole = (data.user?.role_key || "staff") as RoleKey;
    router.push(next || defaultPathForRole(actualRole));
    router.refresh();
  }

  return (
    <form className="login-card" onSubmit={submit}>
      <div className="brand-mark">HO</div>
      <div className="grid"><span className="eyebrow">Staff Payroll</span><h1>Sign in</h1><p className="muted">Use your payroll account.</p></div>
      <div className="field"><label htmlFor="displayName">Display name</label><input id="displayName" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Name" /></div>
      <div className="field"><label htmlFor="secret">Password</label><input id="secret" type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="Password" /></div>
      {error ? <p className="badge danger">{error}</p> : null}
      <button className="primary-button" type="submit">Sign in</button>
    </form>
  );
}
