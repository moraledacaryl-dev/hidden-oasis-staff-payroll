"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { defaultPathForRole } from "@/lib/session-client";
import { roleLabels } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";

const roleOptions: { role: RoleKey; description: string }[] = [
  { role: "owner", description: "Full overview, settings, reports, payroll preview, and owner cockpit." },
  { role: "payroll", description: "Payroll preview, staff list, reports, and cutoff QA." },
  { role: "supervisor", description: "Supervisor queue, staff list, attendance/OT/leave readiness." },
  { role: "staff", description: "Personal staff portal shell. Write actions are not enabled yet." },
];

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [role, setRole] = useState<RoleKey>("owner");
  const [displayName, setDisplayName] = useState("Caryl");
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
      setError("Sign in failed. Use an existing Staff Payroll app user.");
      return;
    }
    const data = await response.json();
    const actualRole = (data.user?.role_key || role) as RoleKey;
    router.push(next || defaultPathForRole(actualRole));
    router.refresh();
  }

  return (
    <form className="login-card" onSubmit={submit}>
      <div className="brand-mark">HO</div>
      <div className="grid"><span className="eyebrow">Staff Payroll</span><h1>Sign in</h1><p className="muted">Use an existing Staff Payroll app user. Backend role decides final access.</p></div>
      <div className="field"><label htmlFor="displayName">Display name</label><input id="displayName" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Existing app user name" /></div>
      <div className="field"><label htmlFor="secret">Password</label><input id="secret" type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="Password" /></div>
      <div className="role-grid">{roleOptions.map((option) => (<label className={`role-option ${role === option.role ? "selected" : ""}`} key={option.role}><input type="radio" name="role" value={option.role} checked={role === option.role} onChange={() => setRole(option.role)} /><strong>{roleLabels[option.role]}</strong><span>{option.description}</span></label>))}</div>
      {error ? <p className="badge danger">{error}</p> : null}
      <button className="primary-button" type="submit">Sign in</button>
    </form>
  );
}
