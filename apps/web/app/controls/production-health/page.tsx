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
  const diskCapacity = health.disk_capacity || [];
  const diskSpaceOK = diskCapacity.length > 0 && diskCapacity.every((entry) => entry.deployment_space_ok);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page system-page">
        <header className="page-header system-hero"><div><span className="eyebrow">System health</span><h1>Production diagnostics</h1><p className="muted">Live database, backup, configuration, and record-count checks. Values are read from the backend health endpoint.</p></div><div className="action-row"><Link className="button ghost" href="/controls">Controls</Link><Link className="button ghost" href="/launch">Readiness</Link></div></header>

        <section className="system-health-grid">
          <div className="system-health-card"><span>Database</span><strong>{health.database_exists ? "Connected" : "Unavailable"}</strong><small>{health.database_checks?.integrity || "No integrity result"}</small></div>
          <div className="system-health-card"><span>Required tables</span><strong>{healthyTables}/{tableChecks.length}</strong><small>Schema presence</small></div>
          <div className="system-health-card"><span>Configuration</span><strong>{configuredSecrets}/{secretChecks.length}</strong><small>Required secrets</small></div>
          <div className="system-health-card"><span>Backups</span><strong>{health.backup_count}</strong><small>{health.latest_backup?.created_at || "No backup found"}</small></div>
          <div className="system-health-card"><span>Release</span><strong>{health.release_verified ? "Verified" : "Not verified"}</strong><small>{health.active_release_sha?.slice(0, 12) || "No active SHA found"}</small></div><div className="system-health-card"><span>Deployment disk space</span><strong>{diskSpaceOK ? "Ready" : "Review needed"}</strong><small>{diskCapacity.length ? `${diskCapacity.length} filesystem(s) checked` : "Capacity data unavailable"}</small></div>
        </section>

        <section className="system-panel">
          <header><div><h2>Deployment storage readiness</h2><p>Live, read-only disk and inode capacity checks using the same minimum limits as the deployment preflight. Passing today does not guarantee enough room for a future build or backup.</p></div></header>
          <div className="system-panel-body">
            <div className="table-wrap"><table>
              <thead><tr><th>Filesystem</th><th>Available</th><th>Free space</th><th>Free inodes</th><th>Deploy minimum</th><th>Result</th></tr></thead>
              <tbody>
                {diskCapacity.map((entry) => <tr key={entry.path}>
                  <td><code>{entry.path}</code></td>
                  <td>{entry.free_gib === undefined ? "—" : `${entry.free_gib.toFixed(2)} GiB`}</td>
                  <td>{entry.free_percent === undefined ? "—" : `${entry.free_percent}%`}</td>
                  <td>{entry.free_inode_percent === undefined ? "—" : `${entry.free_inode_percent}%`}</td>
                  <td>{entry.minimum_free_percent === undefined ? "—" : `${entry.minimum_free_gib} GiB, ${entry.minimum_free_percent}% space, ${entry.minimum_inode_percent}% inodes`}</td>
                  <td>{entry.error ? entry.error : <YesNo value={entry.deployment_space_ok} />}</td>
                </tr>)}
                {diskCapacity.length === 0 ? <tr><td colSpan={6}>Storage status unavailable. Check the server before attempting deployment.</td></tr> : null}
              </tbody>
            </table></div>
            {!diskSpaceOK ? <p className="muted">Storage is below the deployment safety threshold or cannot be inspected. Do not bypass the preflight; review inactive releases and backups on the server.</p> : null}
          </div>
        </section>

        <section className="system-panel">
          <header><div><h2>Production release identity</h2><p>Read-only comparison of the active release, deployment marker, and running API source. The web service and worker still require separate runtime checks.</p></div></header>
          <div className="system-panel-body">
            <div className="table-wrap"><table><tbody>
              <tr><th>Active release SHA</th><td><code>{health.active_release_sha || "Unavailable"}</code></td></tr>
              <tr><th>Deployment marker SHA</th><td><code>{health.deployed_sha || "Unavailable"}</code></td></tr>
              <tr><th>Running API source SHA</th><td><code>{health.running_api_sha || "Unavailable"}</code></td></tr>
              <tr><th>Agreement</th><td><YesNo value={health.release_verified} /></td></tr>
            </tbody></table></div>
          </div>
        </section>
        <section className="system-panel"><header><div><h2>Core paths</h2><p>Server-side locations and the identity used for this check.</p></div></header><div className="system-panel-body"><div className="table-wrap"><table><tbody><tr><th>Database</th><td>{health.database_path || "—"}</td></tr><tr><th>Backup directory</th><td>{health.backup_dir || "—"}</td></tr><tr><th>Checked by</th><td>{health.checked_by || session.display_name}</td></tr></tbody></table></div></div></section>

        <section className="system-grid"><div className="system-panel"><header><div><h2>Required tables</h2><p>Application schema checks.</p></div></header><div className="system-panel-body system-check-list">{tableChecks.map(([key, value]) => <div className="system-check-row" key={key}><strong>{key}</strong><p>Database table</p><YesNo value={value} /></div>)}</div></div><div className="system-panel"><header><div><h2>Configuration</h2><p>Required runtime settings.</p></div></header><div className="system-panel-body system-check-list">{secretChecks.map(([key, value]) => <div className="system-check-row" key={key}><strong>{key}</strong><p>Environment configuration</p><YesNo value={value} /></div>)}<div className="system-check-row"><strong>Backup encryption</strong><p>Encryption configuration</p><YesNo value={health.backup_encryption_configured} /></div><div className="system-check-row"><strong>Off-server backup</strong><p>External recovery copy</p><YesNo value={health.offsite_backup_configured} /></div></div></div></section>

        <section className="system-panel"><header><div><h2>Record counts</h2><p>Current backend totals for operational verification.</p></div></header><div className="system-panel-body"><div className="table-wrap"><table><tbody>{Object.entries(health.counts || {}).map(([key, value]) => <tr key={key}><th>{key}</th><td>{value}</td></tr>)}</tbody></table></div></div></section>
      </div>
    </Shell>
  );
}
