import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getMeta } from "@/lib/api";

async function healthCheck() {
  try {
    const meta = await getMeta();
    return { ok: true, meta };
  } catch (error) {
    return { ok: false, meta: null };
  }
}

export default async function LaunchCenterPage() {
  const health = await healthCheck();
  const checks = [
    { title: "API reachable", ok: health.ok, detail: health.ok ? "Backend responded through the web app." : "Backend did not respond from the web app." },
    { title: "Payroll review pages", ok: true, detail: "Review, reports, audit, and payslip pages are linked from run history." },
    { title: "Release safety", ok: true, detail: "Mark-paid backend is record-only and does not move money." },
    { title: "Backups", ok: false, detail: "Create a fresh database backup before live payroll use." },
    { title: "Service deployment", ok: false, detail: "API and web still need service/process setup before production use." },
  ];

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Launch Center</span>
            <h1>System Health</h1>
            <p className="muted">Read-only launch checklist for the migrated payroll system.</p>
          </div>
          <StatusBadge label={health.ok ? "API online" : "API issue"} tone={health.ok ? "ok" : "danger"} />
        </header>

        <section className="grid cols-3">
          <div className="card metric"><span className="eyebrow">API</span><strong className="metric-value">{health.ok ? "OK" : "Check"}</strong></div>
          <div className="card metric"><span className="eyebrow">Mode</span><strong className="metric-value">Read-only</strong></div>
          <div className="card metric"><span className="eyebrow">Launch</span><strong className="metric-value">Not final</strong></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Checks</h2><p className="muted">Green means ready enough for review. Yellow items should be completed before production.</p></div></div>
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
          <div className="card"><h2>Payroll quick links</h2><div className="action-list"><Link className="action-item" href="/payroll/runs">Run history</Link><Link className="action-item" href="/cutoff">Cutoff draft</Link><Link className="action-item" href="/payroll/runs/1/reports">Latest report sample</Link><Link className="action-item" href="/payroll/runs/1/payslips">Latest payslip sample</Link></div></div>
          <div className="card"><h2>Before live use</h2><div className="action-list"><div className="action-item"><strong>Backup database</strong><p className="muted">Download a fresh backup before marking payroll as paid.</p></div><div className="action-item"><strong>Restart as service</strong><p className="muted">Manual terminal sessions are not production-safe.</p></div><div className="action-item"><strong>Compare with old app</strong><p className="muted">Confirm totals, deductions, and payslips against the previous working system.</p></div></div></div>
        </section>
      </div>
    </Shell>
  );
}
