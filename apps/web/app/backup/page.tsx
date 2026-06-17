import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";

export default async function BackupCenterPage() {
  const checks = [
    { title: "Database copy", detail: "Keep a fresh data/staff_payroll.sqlite backup." },
    { title: "Export bundle", detail: "Keep CSV exports and schema.sql with it." },
    { title: "Off-server copy", detail: "Store one copy outside the server." },
    { title: "Restore path", detail: "Know where the database goes before restart." },
  ];
  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Backup Center</span><h1>Data Safety</h1><p className="muted">Recovery checks before payroll changes.</p></div>
          <StatusBadge label="manual backup" tone="warning" />
        </header>
        <section className="grid cols-3">
          <div className="card metric"><span className="eyebrow">Database</span><strong className="metric-value">SQLite</strong></div>
          <div className="card metric"><span className="eyebrow">Risk</span><strong className="metric-value">Data loss</strong></div>
          <div className="card metric"><span className="eyebrow">Status</span><strong className="metric-value">Check</strong></div>
        </section>
        <section className="card"><div className="panel-title"><div><h2>Backup checklist</h2><p className="muted">Run before migrations or paid marking.</p></div></div><div className="action-list">{checks.map((check)=>(<div className="action-item" key={check.title}><strong>{check.title}</strong><p className="muted">{check.detail}</p></div>))}</div></section>
        <section className="grid cols-2">
          <div className="card"><h2>Backup targets</h2><div className="action-list"><div className="action-item"><strong>Server archive</strong><p className="muted">Create before risky changes.</p></div><div className="action-item"><strong>Off-server copy</strong><p className="muted">Required for real recovery.</p></div></div></div>
          <div className="card"><h2>Quick links</h2><div className="action-list"><Link className="action-item" href="/launch">Launch center</Link><Link className="action-item" href="/payroll/runs">Payroll runs</Link><Link className="action-item" href="/settings">Settings</Link></div></div>
        </section>
        <section className="card"><h2>Restore reminder</h2><p className="muted">Stop the API, replace data/staff_payroll.sqlite, restart the API. Copy current live data first.</p></section>
      </div>
    </Shell>
  );
}
