import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, getMeta } from "@/lib/api";
import Link from "next/link";

export default async function SettingsPage() {
  const meta = await getMeta();

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Settings</span><h1>Migration controls</h1><p className="muted">Current migration boundary, API connection status, and owner-only access tools.</p><div className="action-row"><Link className="button ghost" href="/settings/users">Manage users</Link><Link className="button ghost" href="/settings/password">My password</Link></div></div><StatusBadge label="guardrails active" /></header>
        <section className="grid cols-2"><div className="card"><div className="panel-title"><h2>API connection</h2></div><div className="action-list"><div className="action-item"><strong>API base URL</strong><p className="muted">{apiBaseUrl()}</p></div><div className="action-item"><strong>API version</strong><p className="muted">{meta.api_version}</p></div><div className="action-item"><strong>Database exists</strong><p className="muted">{String(meta.database_exists)}</p></div><div className="action-item"><strong>Database path</strong><p className="muted">{meta.database_path}</p></div></div></div><div className="card"><div className="panel-title"><h2>Do-not-break list</h2></div><div className="action-list"><div className="action-item"><strong>No database rewrite first.</strong><p className="muted">SQLite stays until UI/API are verified.</p></div><div className="action-item"><strong>No payroll formula rewrite.</strong><p className="muted">Existing Python engine remains source of truth.</p></div><div className="action-item"><strong>Writes stay role-enforced.</strong><p className="muted">Schedule, payroll lifecycle, corrections, and user actions are guarded by backend roles.</p></div><div className="action-item"><strong>Streamlit fallback stays.</strong><p className="muted">Retire Streamlit last, not first.</p></div></div></div></section>
        <section className="footer-note">Next stage after this shell runs: compare payroll preview totals from Next.js against Streamlit for the same cutoff, then add authenticated write endpoints one workflow at a time.</section>
      </div>
    </Shell>
  );
}
