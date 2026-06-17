import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getMeta, getPayrollRuns } from "@/lib/api";
import { currentSession } from "@/lib/session";

async function healthCheck() {
  try {
    const meta = await getMeta();
    return { ok: true, meta };
  } catch (error) {
    return { ok: false, meta: null };
  }
}

export default async function LaunchCenterPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner") {
    return <Shell allowedRoles={["owner"]}><div /></Shell>;
  }
  const health = await healthCheck();
  const runs = health.ok ? await getPayrollRuns().catch(() => []) : [];
  const latestRun = runs[0];
  const checks = [
    { title: "API", ok: health.ok, detail: health.ok ? "Online" : "Check backend" },
    { title: "Payroll pages", ok: true, detail: "Runs, audit, reports, payslips" },
    { title: "Paid marker", ok: true, detail: "Owner-only record" },
    { title: "Backups", ok: false, detail: "Run before payroll changes" },
    { title: "Services", ok: false, detail: "Use systemd in production" },
  ];

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Launch</span>
            <h1>System health</h1>
            <p className="muted">Deployment checks.</p>
          </div>
          <StatusBadge label={health.ok ? "API online" : "API issue"} tone={health.ok ? "ok" : "danger"} />
        </header>

        <section className="grid cols-3">
          <div className="card metric"><span className="eyebrow">API</span><strong className="metric-value">{health.ok ? "OK" : "Check"}</strong></div>
          <div className="card metric"><span className="eyebrow">Runs</span><strong className="metric-value">{runs.length}</strong></div>
          <div className="card metric"><span className="eyebrow">Launch</span><strong className="metric-value">Check</strong></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Checks</h2><p className="muted">Finish yellow items before live payroll.</p></div></div>
          <div className="action-list">
            {checks.map((check) => (
              <div className="action-item" key={check.title}>
                <div className="panel-title"><strong>{check.title}</strong><StatusBadge label={check.ok ? "OK" : "Needed"} tone={check.ok ? "ok" : "warning"} /></div>
                <p className="muted">{check.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid cols-2">
          <div className="card"><h2>Payroll links</h2><div className="action-list"><Link className="action-item" href="/payroll/runs">Run history</Link><Link className="action-item" href="/cutoff">Cutoff</Link>{latestRun ? <Link className="action-item" href={`/payroll/runs/${latestRun.id}/reports`}>Latest report</Link> : null}{latestRun ? <Link className="action-item" href={`/payroll/runs/${latestRun.id}/payslips`}>Latest payslips</Link> : null}</div></div>
          <div className="card"><h2>Before live use</h2><div className="action-list"><div className="action-item"><strong>Backup</strong><p className="muted">Fresh database copy.</p></div><div className="action-item"><strong>Services</strong><p className="muted">API and web under systemd.</p></div><div className="action-item"><strong>Compare</strong><p className="muted">Confirm totals and payslips.</p></div></div></div>
        </section>
      </div>
    </Shell>
  );
}
