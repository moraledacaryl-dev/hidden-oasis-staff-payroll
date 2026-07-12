import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getProductionHealth, type ProductionHealth } from "@/lib/api";
import { currentSession } from "@/lib/session";

function YesNo({ value }: { value?: boolean }) {
  return <StatusBadge label={value ? "Yes" : "No"} tone={value ? "ok" : "danger"} />;
}

export default async function ProductionHealthPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;

  let health: ProductionHealth;
  try {
    health = await getProductionHealth();
  } catch (error) {
    return <Shell allowedRoles={["owner", "payroll"]}><div className="page"><section className="card"><strong>Production health unavailable</strong><p className="muted">{error instanceof Error ? error.message : "Try again shortly."}</p></section></div></Shell>;
  }

  const tableChecks = Object.entries(health.tables || {});
  const secretChecks = Object.entries(health.secrets_configured || {});
  const healthyTables = tableChecks.filter(([, value]) => value).length;
  const configuredSecrets = secretChecks.filter(([, value]) => value).length;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page system-page">
        <header className="page-header system-hero"><div><span className="eyebrow">System health</span><h1>Production diagnostics</h1><p className="muted">Live database, backup, configuration, and record-count checks. Values are read from the backend health endpoint.</p></div><div className="action-row"><Link className="button ghost" href="/controls">Controls</Link><Link className="button ghost" href="/launch">Readiness</Link></div></header>

        <section className="system-health-grid">
          <div className="system-health-card"><span>Database</span><strong>{health.database_exists ? "Connected" : "Unavailable"}</strong><small>{health.database_checks?.integrity || "No integrity result"}</small></div>
          <div className="system-health-card"><span>Required tables</span><strong>{healthyTables}/{tableChecks.length}</strong><small>Schema presence</small></div>
          <div className="system-health-card"><span>Configuration</span><strong>{configuredSecrets}/{secretChecks.length}</strong><small>Required secrets</small></div>
          <div className="system-health-card"><span>Backups</span><strong>{health.backup_count}</strong><small>{health.latest_backup?.created_at || "No backup found"}</small></div>
        </section>

        <section className="system-panel"><header><div><h2>Core paths</h2><p>Server-side locations and the identity used for this check.</p></div></header><div className="system-panel-body"><div className="table-wrap"><table><tbody><tr><th>Database</th><td>{health.database_path || "—"}</td></tr><tr><th>Backup directory</th><td>{health.backup_dir || "—"}</td></tr><tr><th>Checked by</th><td>{health.checked_by || session.display_name}</td></tr></tbody></table></div></div></section>

        <section className="system-grid"><div className="system-panel"><header><div><h2>Required tables</h2><p>Application schema checks.</p></div></header><div className="system-panel-body system-check-list">{tableChecks.map(([key, value]) => <div className="system-check-row" key={key}><strong>{key}</strong><p>Database table</p><YesNo value={value} /></div>)}</div></div><div className="system-panel"><header><div><h2>Configuration</h2><p>Required runtime settings.</p></div></header><div className="system-panel-body system-check-list">{secretChecks.map(([key, value]) => <div className="system-check-row" key={key}><strong>{key}</strong><p>Environment configuration</p><YesNo value={value} /></div>)}<div className="system-check-row"><strong>Backup encryption</strong><p>Encryption configuration</p><YesNo value={health.backup_encryption_configured} /></div><div className="system-check-row"><strong>Off-server backup</strong><p>External recovery copy</p><YesNo value={health.offsite_backup_configured} /></div></div></div></section>

        <section className="system-panel"><header><div><h2>Record counts</h2><p>Current backend totals for operational verification.</p></div></header><div className="system-panel-body"><div className="table-wrap"><table><tbody>{Object.entries(health.counts || {}).map(([key, value]) => <tr key={key}><th>{key}</th><td>{value}</td></tr>)}</tbody></table></div></div></section>
      </div>
    </Shell>
  );
}
