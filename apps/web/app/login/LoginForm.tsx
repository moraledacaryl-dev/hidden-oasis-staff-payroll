"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { defaultPathForRole, NAME_COOKIE, ROLE_COOKIE } from "@/lib/session";
import { roleLabels } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";

const roleOptions: { role: RoleKey; description: string }[] = [
  { role: "owner", description: "Full overview, settings, reports, payroll preview, and owner cockpit." },
  { role: "payroll", description: "Payroll preview, staff list, reports, and cutoff QA." },
  { role: "supervisor", description: "Supervisor queue, staff list, attendance/OT/leave readiness." },
  { role: "staff", description: "Personal staff portal shell. Write actions are not enabled yet." },
];

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=43200; SameSite=Lax`;
}

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [role, setRole] = useState<RoleKey>("owner");
  const [name, setName] = useState("Caryl");
  const next = useMemo(() => searchParams.get("next"), [searchParams]);

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCookie(ROLE_COOKIE, role);
    setCookie(NAME_COOKIE, name.trim() || roleLabels[role]);
    router.push(next || defaultPathForRole(role));
    router.refresh();
  }

  return (
    <form className="login-card" onSubmit={submit}>
      <div className="brand-mark">HO</div>
      <div className="grid">
        <span className="eyebrow">Staff Payroll</span>
        <h1>Choose your workspace</h1>
        <p className="muted">
          This is the migration role shell. It controls the Next.js interface only; real password authentication will connect to the backend after the API auth endpoints are added.
        </p>
      </div>

      <div className="field">
        <label htmlFor="name">Display name</label>
        <input id="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" />
      </div>

      <div className="role-grid">
        {roleOptions.map((option) => (
          <label className={`role-option ${role === option.role ? "selected" : ""}`} key={option.role}>
            <input
              type="radio"
              name="role"
              value={option.role}
              checked={role === option.role}
              onChange={() => setRole(option.role)}
            />
            <strong>{roleLabels[option.role]}</strong>
            <span>{option.description}</span>
          </label>
        ))}
      </div>

      <button className="primary-button" type="submit">Enter workspace</button>
    </form>
  );
}
