import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { getProductionHealth, type ProductionHealth } from "@/lib/api";
import { currentSession } from "@/lib/session";

function YesNo({ value }: { value?: boolean }) {
  return <span className={value ? "badge ok" : "badge danger"}>{value ? "Yes" : "No"}</span>;
}

export default async function ProductionHealthPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }

  let health: ProductionHealth;
  try {
    health = await getProductionHealth();
  } catch (error) {
    return (
      <Shell allowedRoles={["owner", "payroll"]}>
        <div className="page"><section className="card"><strong>Production health unavailable</strong><p className="muted">{error instanceof Error ? error.message : "Try again shortly."}</p></section></div>
      </Shell>
    );
  }

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div><span className="eyebrow">Controls</span><h1>Production health</h1></div>
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>Database exists</strong><p><YesNo value={health.database_exists} /></p></div>
          <div className="card"><strong>Backups found</strong><p>{health.backup_count}</p></div>
          <div className="card"><strong>Latest backup</strong><p>{health.latest_backup?.created_at || "None"}</p></div>
        </section>

        <section className="card">
          <h2>Core paths</h2>
          <div className="table-wrap"><table><tbody>
            <tr><th>Database</th><td>{health.database_path || "—"}</td></tr>
            <tr><th>Backup directory</th><td>{health.backup_dir || "—"}</td></tr>
            <tr><th>Checked by</th><td>{health.checked_by || session.display_name}</td></tr>
          </tbody></table></div>
        </section>

        <section className="grid cols-2">
          <div className="card">
            <h2>Required tables</h2>
            <div className="table-wrap"><table><tbody>
              {Object.entries(health.tables || {}).map(([key, value]) => <tr key={key}><th>{key}</th><td><YesNo value={value} /></td></tr>)}
            </tbody></table></div>
          </div>
          <div className="card">
            <h2>Configuration</h2>
            <div className="table-wrap"><table><tbody>
              {Object.entries(health.secrets_configured || {}).map(([key, value]) => <tr key={key}><th>{key}</th><td><YesNo value={value} /></td></tr>)}
              <tr><th>Backup encryption</th><td><YesNo value={health.backup_encryption_configured} /></td></tr>
              <tr><th>Off-server backup</th><td><YesNo value={health.offsite_backup_configured} /></td></tr>
            </tbody></table></div>
          </div>
        </section>

        <section className="card">
          <h2>Record counts</h2>
          <div className="table-wrap"><table><tbody>
            {Object.entries(health.counts || {}).map(([key, value]) => <tr key={key}><th>{key}</th><td>{value}</td></tr>)}
          </tbody></table></div>
        </section>
      </div>
    </Shell>
  );
}
