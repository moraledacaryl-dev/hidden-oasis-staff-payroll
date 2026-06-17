import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, getMeta } from "@/lib/api";
import Link from "next/link";

export default async function SettingsPage() {
  const meta = await getMeta();

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Settings</span><h1>System settings</h1><p className="muted">API status and access tools.</p><div className="action-row"><Link className="button ghost" href="/settings/users">Users</Link><Link className="button ghost" href="/settings/password">Password</Link></div></div><StatusBadge label="active" /></header>
        <section className="grid cols-2"><div className="card"><div className="panel-title"><h2>API</h2></div><div className="action-list"><div className="action-item"><strong>Base URL</strong><p className="muted">{apiBaseUrl()}</p></div><div className="action-item"><strong>Version</strong><p className="muted">{meta.api_version}</p></div><div className="action-item"><strong>Database</strong><p className="muted">{String(meta.database_exists)}</p></div><div className="action-item"><strong>Path</strong><p className="muted">{meta.database_path}</p></div></div></div><div className="card"><div className="panel-title"><h2>Rules</h2></div><div className="action-list"><div className="action-item"><strong>SQLite source</strong><p className="muted">No database files in Git.</p></div><div className="action-item"><strong>Python payroll</strong><p className="muted">Formula source of truth.</p></div><div className="action-item"><strong>Backend roles</strong><p className="muted">Required for writes.</p></div><div className="action-item"><strong>Backup first</strong><p className="muted">Before migration or paid marking.</p></div></div></div></section>
      </div>
    </Shell>
  );
}
