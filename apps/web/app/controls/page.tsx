import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { getPayrollRuns } from "@/lib/api";
import { currentSession } from "@/lib/session";

export default async function OperationsControlsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  const runs = await getPayrollRuns();
  const recentRuns = runs.slice(0, 4);
  const activeRuns = runs.filter((run) => ["Draft", "For Owner Review", "Approved"].includes(run.status)).length;
  const paidRuns = runs.filter((run) => ["Paid", "Released"].includes(run.status)).length;

  return <Shell allowedRoles={["owner", "payroll"]}><div className="page system-page">
    <header className="system-hero"><div><span className="eyebrow">System</span><h1>Controls and readiness</h1><p className="muted">Operational entry points for payroll, backups, production health, and controlled maintenance.</p></div><div className="system-actions"><Link className="button ghost" href="/controls/production-health">Production health</Link><Link className="button" href="/backup">Backups</Link></div></header>
    <section className="system-kpis"><div className="system-kpi"><span>Saved payroll runs</span><strong>{runs.length}</strong><small>All lifecycle states</small></div><div className="system-kpi"><span>Active workflow</span><strong>{activeRuns}</strong><small>Draft through approved</small></div><div className="system-kpi"><span>Paid history</span><strong>{paidRuns}</strong><small>Immutable payout records</small></div><div className="system-kpi"><span>System role</span><strong>{session.role_key}</strong><small>Current access level</small></div></section>
    <section className="system-grid">
      <article className="system-panel"><header><div><h2>Payroll controls</h2><p>Use canonical workflows rather than direct data edits.</p></div></header><div className="system-panel-body system-catalog"><Link className="system-link" href="/cutoff"><div><strong>Cutoff control</strong><small>Readiness, blockers, and draft creation</small></div><span>Open</span></Link><Link className="system-link" href="/payroll"><div><strong>Payroll preview</strong><small>Calculated payroll before saving</small></div><span>Open</span></Link><Link className="system-link" href="/payroll/runs"><div><strong>Payroll runs</strong><small>Review, approve, pay, revise, and audit</small></div><span>Open</span></Link></div></article>
      <article className="system-panel"><header><div><h2>System controls</h2><p>Owner-safe operational and maintenance workspaces.</p></div></header><div className="system-panel-body system-catalog"><Link className="system-link" href="/launch"><div><strong>Launch readiness</strong><small>Application readiness and deployment checks</small></div><span>Open</span></Link><Link className="system-link" href="/backup"><div><strong>Backups</strong><small>Create, verify, and download backups</small></div><span>Open</span></Link><Link className="system-link" href="/settings"><div><strong>Settings and access</strong><small>Users, security, and system information</small></div><span>Open</span></Link><Link className="system-link" href="/controls/old-schedules"><div><strong>Legacy schedules</strong><small>Historical schedule compatibility</small></div><span>Open</span></Link></div></article>
      <article className="system-panel"><header><div><h2>Recent payroll runs</h2><p>Latest saved lifecycle records.</p></div></header><div className="system-panel-body system-catalog">{recentRuns.map((run) => <Link className="system-link" href={`/payroll/runs/${run.id}`} key={run.id}><div><strong>Run #{run.id}</strong><small>{run.period_start} to {run.period_end}</small></div><span>{run.status}</span></Link>)}{!recentRuns.length ? <p className="muted">No saved payroll runs.</p> : null}</div></article>
      <article className="system-panel"><header><div><h2>Control principles</h2><p>Existing safeguards remain part of the workflow.</p></div></header><div className="system-panel-body"><div className="system-note">Paid payroll runs remain immutable. Corrections use revisions, schedule and attendance changes remain auditable, and backup verification is separate from backup creation.</div></div></article>
    </section>
  </div></Shell>;
}
