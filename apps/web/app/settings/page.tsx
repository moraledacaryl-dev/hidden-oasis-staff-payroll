import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, getMeta } from "@/lib/api";
import Link from "next/link";
import { currentSession } from "@/lib/session";
import { redirect } from "next/navigation";

export default async function SettingsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner") return <Shell allowedRoles={["owner"]}><div /></Shell>;
  const meta = await getMeta();

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">System</span><h1>Settings</h1><div className="action-row"><Link className="button ghost" href="/settings/users">Users</Link><Link className="button ghost" href="/settings/security">Security</Link><Link className="button ghost" href="/backup">Backups</Link></div></div><StatusBadge label="active" /></header>
        <section className="card"><div className="panel-title"><h2>System</h2></div><div className="action-list"><div className="action-item"><strong>API</strong><p className="muted">{apiBaseUrl()}</p></div><div className="action-item"><strong>Version</strong><p className="muted">{meta.api_version}</p></div><div className="action-item"><strong>Database</strong><p className="muted">{meta.database_exists ? "Connected" : "Unavailable"}</p></div><div className="action-item"><strong>Path</strong><p className="muted">{meta.database_path}</p></div></div></section>
      </div>
    </Shell>
  );
}
