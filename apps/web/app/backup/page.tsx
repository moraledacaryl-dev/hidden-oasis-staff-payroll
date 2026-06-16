import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";

export default async function BackupCenterPage() {
  const checks = [
    { title: "Database backup exists", detail: "Keep a fresh copy of data/staff_payroll.sqlite before live payroll actions." },
    { title: "Export bundle saved", detail: "Keep CSV exports and schema.sql together with the SQLite file." },
    { title: "Mac copy downloaded", detail: "Store a copy outside the server so a server failure does not lose the only backup." },
    { title: "Restore path documented", detail: "Know where to place the database before restarting the API." },
  ];
  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Backup Center</span><h1>Data Safety</h1><p className="muted">Recovery checklist before using the migrated payroll system live.</p></div>
          <StatusBadge label="manual backup" tone="warning" />
        </header>
        <section className="grid cols-3">
          <div className="card metric"><span className="eyebrow">Database</span><strong className="metric-value">SQLite</strong></div>
          <div className="card metric"><span className="eyebrow">Risk</span><strong className="metric-value">Data loss</strong></div>
          <div className="card metric"><span className="eyebrow">Status</span><strong className="metric-value">Check</strong></div>
        </section>
        <section className="card"><div className="panel-title"><div><h2>Backup checklist</h2><p className="muted">Complete these before final payroll use.</p></div></div><div className="action-list">{checks.map((check)=>(<div className="action-item" key={check.title}><strong>{check.title}</strong><p className="muted">{check.detail}</p></div>))}</div></section>
        <section className="grid cols-2">
          <div className="card"><h2>Current known backup</h2><div className="action-list"><div className="action-item"><strong>Server archive</strong><p className="muted">data/backups/staff_payroll_backup_20260616T031246Z.tar.gz</p></div><div className="action-item"><strong>Mac copy</strong><p className="muted">~/Downloads/staff-payroll-backups/staff_payroll_backup_20260616T031246Z.tar.gz</p></div></div></div>
          <div className="card"><h2>Quick links</h2><div className="action-list"><Link className="action-item" href="/launch">Launch center</Link><Link className="action-item" href="/payroll/runs">Payroll runs</Link><Link className="action-item" href="/payroll/runs/1/audit">Audit sample</Link></div></div>
        </section>
        <section className="card"><h2>Restore reminder</h2><p className="muted">Stop the API, replace data/staff_payroll.sqlite with the backup database, then restart the API. Do not restore over live data without first copying the current database.</p></section>
      </div>
    </Shell>
  );
}
