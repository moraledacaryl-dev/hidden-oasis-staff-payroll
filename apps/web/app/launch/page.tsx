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
  if (session.role_key !== "owner") return <Shell allowedRoles={["owner"]}><div /></Shell>;

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
  const passed = checks.filter((check) => check.ok).length;
  const ready = health.ok && passed === checks.length;

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page system-page">
        <header className="page-header system-hero">
          <div><span className="eyebrow">Readiness</span><h1>Launch and production readiness</h1><p className="muted">Use live system checks only. Resolve missing configuration or backup coverage before treating the application as fully production-ready.</p></div>
          <div className="action-row"><StatusBadge label={ready ? "ready" : "needs attention"} tone={ready ? "ok" : "warning"} /><Link className="button ghost" href="/controls/production-health">Full health details</Link></div>
        </header>

        <section className="system-health-grid">
          <div className="system-health-card"><span>API</span><strong>{health.ok ? "Online" : "Issue"}</strong><small>Current backend response</small></div>
          <div className="system-health-card"><span>Checks passed</span><strong>{passed}/{checks.length}</strong><small>Readiness requirements</small></div>
          <div className="system-health-card"><span>Backups</span><strong>{health.health?.backup_count || 0}</strong><small>Server-visible copies</small></div>
          <div className="system-health-card"><span>Payroll runs</span><strong>{runs.length}</strong><small>Saved workflow history</small></div>
        </section>

        <section className="system-panel"><header><div><h2>Production checklist</h2><p>Each line is derived from the live health endpoint.</p></div><StatusBadge label={ready ? "all clear" : `${checks.length - passed} remaining`} tone={ready ? "ok" : "warning"} /></header><div className="system-panel-body system-check-list">{checks.map((check) => <div className="system-check-row" key={check.title}><strong>{check.title}</strong><p>{check.detail}</p><StatusBadge label={check.ok ? "OK" : "Needed"} tone={check.ok ? "ok" : "warning"} /></div>)}</div></section>

        <section className="system-panel"><header><div><h2>Operational verification</h2><p>Open the canonical workspaces rather than duplicating controls here.</p></div></header><div className="system-panel-body system-catalog"><Link className="system-link-card" href="/backup"><strong>Backups</strong><span>Create, verify, and download recovery files.</span></Link><Link className="system-link-card" href="/settings"><strong>Settings</strong><span>Review backend and database status.</span></Link><Link className="system-link-card" href="/payroll/runs"><strong>Payroll runs</strong><span>Review lifecycle and immutable paid history.</span></Link>{latestRun ? <Link className="system-link-card" href={`/payroll/runs/${latestRun.id}/audit`}><strong>Latest audit</strong><span>Inspect the newest run timeline.</span></Link> : null}</div></section>
      </div>
    </Shell>
  );
}
