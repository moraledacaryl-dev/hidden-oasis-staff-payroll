import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

type ProductionHealth = {
  ok: boolean;
  checked_by?: string;
  database_path?: string;
  database_exists?: boolean;
  backup_dir?: string;
  backup_count?: number;
  latest_backup?: string | null;
  tables?: Record<string, boolean>;
  counts?: Record<string, number>;
  secrets_configured?: Record<string, boolean>;
  mode?: string;
};

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function getProductionHealth(): Promise<ProductionHealth> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return { ok: false };
  const res = await fetch(`${apiBaseUrl()}/api/v1/production/health`, {
    headers: {
      Authorization: `Bearer ${token}`,
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
    cache: "no-store",
  });
  if (!res.ok) return { ok: false };
  return res.json();
}

function YesNo({ value }: { value?: boolean }) {
  return <span className={value ? "badge ok" : "badge danger"}>{value ? "Yes" : "No"}</span>;
}

export default async function ProductionHealthPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const health = await getProductionHealth();
  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div>
            <span className="eyebrow">Controls</span>
            <h1>Production Health</h1>
            <p className="muted">Read-only deployment, database, backup, and safety summary. Secret values are never displayed.</p>
          </div>
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>Database exists</strong><p><YesNo value={health.database_exists} /></p></div>
          <div className="card"><strong>Backups found</strong><p>{health.backup_count ?? 0}</p></div>
          <div className="card"><strong>Latest backup</strong><p className="muted">{health.latest_backup || "None found"}</p></div>
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
            <h2>Configured secrets</h2>
            <div className="table-wrap"><table><tbody>
              {Object.entries(health.secrets_configured || {}).map(([key, value]) => <tr key={key}><th>{key}</th><td><YesNo value={value} /></td></tr>)}
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
