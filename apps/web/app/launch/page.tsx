import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRuns, getProductionHealth } from "@/lib/api";
import { currentSession } from "@/lib/session";

async function healthCheck() {
  try {
    const health = await getProductionHealth();
    return { ok: health.ok, health };
  } catch {
    return { ok: false, health: null };
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
    { title: "Database", ok: Boolean(health.health?.database_exists && health.health?.database_checks.integrity === "ok"), detail: health.health?.database_checks.integrity || "Unavailable" },
    { title: "Writes", ok: Boolean(health.health?.database_checks.writable), detail: health.health?.database_checks.writable ? "Ready" : "Unavailable" },
    { title: "Migrations", ok: Number(health.health?.database_checks.migration_version || 0) > 0, detail: `Version ${health.health?.database_checks.migration_version || 0}` },
    { title: "Backup", ok: Number(health.health?.backup_count || 0) > 0 && Number(health.health?.backup_age_hours || 999) <= 24, detail: health.health?.latest_backup?.created_at || "No backup" },
    { title: "Encryption", ok: Boolean(health.health?.backup_encryption_configured), detail: health.health?.backup_encryption_configured ? "Configured" : "Not configured" },
    { title: "Off-server copy", ok: Boolean(health.health?.offsite_backup_configured), detail: health.health?.offsite_backup_configured ? "Configured" : "Not configured" },
  ];

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Launch</span>
            <h1>System health</h1>
          </div>
          <StatusBadge label={health.ok ? "API online" : "API issue"} tone={health.ok ? "ok" : "danger"} />
        </header>

        <section className="grid cols-3">
          <div className="card metric"><span className="eyebrow">API</span><strong className="metric-value">{health.ok ? "OK" : "Check"}</strong></div>
          <div className="card metric"><span className="eyebrow">Runs</span><strong className="metric-value">{runs.length}</strong></div>
          <div className="card metric"><span className="eyebrow">Checks</span><strong className="metric-value">{checks.filter((check) => check.ok).length}/{checks.length}</strong></div>
        </section>

        <section className="card">
          <div className="panel-title"><h2>Checks</h2></div>
          <div className="action-list">
            {checks.map((check) => (
              <div className="action-item" key={check.title}>
                <div className="panel-title"><strong>{check.title}</strong><StatusBadge label={check.ok ? "OK" : "Needed"} tone={check.ok ? "ok" : "warning"} /></div>
                <p className="muted">{check.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="card"><h2>Payroll</h2><div className="action-list"><Link className="action-item" href="/payroll/runs">Run history</Link><Link className="action-item" href="/cutoff">Cutoff</Link>{latestRun ? <Link className="action-item" href={`/payroll/runs/${latestRun.id}/reports`}>Latest report</Link> : null}{latestRun ? <Link className="action-item" href={`/payroll/runs/${latestRun.id}/payslips`}>Latest payslips</Link> : null}</div></section>
      </div>
    </Shell>
  );
}
