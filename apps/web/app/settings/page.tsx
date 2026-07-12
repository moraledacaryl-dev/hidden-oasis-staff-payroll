import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { apiBaseUrl, getMeta } from "@/lib/api";
import { currentSession } from "@/lib/session";

export default async function SettingsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner") return <Shell allowedRoles={["owner"]}><div /></Shell>;
  const meta = await getMeta();
  const databaseStatus = meta.database_exists ? "Connected" : "Unavailable";

  return <Shell allowedRoles={["owner"]}><div className="page system-page">
    <header className="system-hero"><div><span className="eyebrow">System</span><h1>Settings</h1><p className="muted">System information, user access, account security, and recovery controls.</p></div><div className="system-actions"><Link className="button ghost" href="/controls">System controls</Link><Link className="button" href="/settings/users">Manage users</Link></div></header>
    <nav className="settings-tabs" aria-label="Settings sections"><Link aria-current="page" href="/settings">Overview</Link><Link href="/settings/users">Users</Link><Link href="/settings/security">Security</Link><Link href="/settings/password">Password</Link><Link href="/backup">Backups</Link></nav>
    <section className="system-kpis"><div className="system-kpi"><span>API version</span><strong>{meta.api_version || "—"}</strong><small>Backend-reported version</small></div><div className="system-kpi"><span>Database</span><strong>{databaseStatus}</strong><small>Current backend status</small></div><div className="system-kpi"><span>Owner access</span><strong>Active</strong><small>Current authenticated role</small></div><div className="system-kpi"><span>Recovery</span><strong>Available</strong><small>Backup workspace enabled</small></div></section>
    <section className="settings-card-list"><article className="settings-card"><h2>System information</h2><p>Values are reported by the active backend.</p><div className="settings-facts"><div className="settings-fact"><div><strong>API endpoint</strong></div><span>{apiBaseUrl()}</span></div><div className="settings-fact"><div><strong>API version</strong></div><span>{meta.api_version || "—"}</span></div><div className="settings-fact"><div><strong>Database</strong></div><span>{databaseStatus}</span></div><div className="settings-fact"><div><strong>Database path</strong></div><span>{meta.database_path || "—"}</span></div></div></article><article className="settings-card"><h2>Access and security</h2><p>Use dedicated workflows for privileged changes.</p><div className="settings-facts"><Link className="settings-fact" href="/settings/users"><div><strong>User management</strong></div><span>Roles, employee links, activation</span></Link><Link className="settings-fact" href="/settings/security"><div><strong>Security</strong></div><span>MFA and account protection</span></Link><Link className="settings-fact" href="/settings/password"><div><strong>Password</strong></div><span>Change current password</span></Link><Link className="settings-fact" href="/backup"><div><strong>Backups</strong></div><span>Create, verify, download</span></Link></div></article></section>
  </div></Shell>;
}
