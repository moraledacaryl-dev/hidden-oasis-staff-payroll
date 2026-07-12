import Link from "next/link";
import { redirect } from "next/navigation";
import { BackupManager } from "@/components/BackupManager";
import { Shell } from "@/components/Shell";
import { currentSession } from "@/lib/session";

export default async function BackupPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner") return <Shell allowedRoles={["owner"]}><div /></Shell>;

  return <Shell allowedRoles={["owner"]}><div className="page system-page">
    <header className="system-hero"><div><span className="eyebrow">System</span><h1>Backups</h1><p className="muted">Create a backup, verify its integrity independently, and retain downloadable recovery files.</p></div><div className="system-actions"><Link className="button ghost" href="/controls/production-health">Production health</Link><Link className="button ghost" href="/controls">System controls</Link></div></header>
    <section className="system-kpis"><div className="system-kpi"><span>Access</span><strong>Owner</strong><small>Restricted operation</small></div><div className="system-kpi"><span>Creation</span><strong>Manual</strong><small>Explicit backup action</small></div><div className="system-kpi"><span>Verification</span><strong>Separate</strong><small>Integrity check required</small></div><div className="system-kpi"><span>Recovery</span><strong>Download</strong><small>Files remain exportable</small></div></section>
    <section className="backup-shell"><header><div><h2>Backup history</h2><p>Encryption status is shown from the real backup metadata; no storage claim is inferred.</p></div></header><div className="backup-body"><BackupManager /></div></section>
  </div></Shell>;
}
