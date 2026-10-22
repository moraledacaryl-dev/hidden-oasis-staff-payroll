import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRunHistory, getProductionHealth } from "@/lib/api";
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
  const history = health.ok ? await getPayrollRunHistory({ page: 1, pageSize: 1 }).catch(() => null) : null;
  const latestRun = history?.items[0];
  const backup = health.health?.latest_backup;
  const backupAgeLimit = health.health?.backup_max_age_hours ?? 26;
  const backupAge = health.health?.backup_age_hours;
  const disks = health.health?.disk_capacity || [];
  const offsiteStatus = health.health?.offsite_backup_configuration_status;
  const offsiteDetail = offsiteStatus === "s3_configured_not_verified"
    ? "S3 configured; remote copy not verified"
    : offsiteStatus === "directory_configured"
      ? "Directory configured; copy not verified"
      : offsiteStatus === "s3_configuration_incomplete"
        ? "S3 configuration incomplete"
        : "No offsite destination configured";
  const checks = [
    { title: "Database", ok: Boolean(health.health?.database_exists && health.health?.database_checks.integrity === "ok"), detail: health.health?.database_checks.integrity || "Unavailable" },
    { title: "Writes", ok: Boolean(health.health?.database_checks.writable), detail: health.health?.database_checks.writable ? "Ready" : "Unavailable" },
    { title: "Migrations", ok: Number(health.health?.database_checks.migration_version || 0) > 0, detail: `Version ${health.health?.database_checks.migration_version || 0}` },
    { title: "Local backup metadata", ok: Boolean(backup?.encrypted && health.health?.backup_encryption_configured && backupAge !== null && backupAge !== undefined && backupAge <= backupAgeLimit), detail: backup ? `Encrypted: ${backup.encrypted ? "yes" : "no"}; age ${backupAge ?? "unknown"}h; limit ${backupAgeLimit}h` : "No local backup" },
    { title: "Backup encryption key", ok: Boolean(health.health?.backup_encryption_configured), detail: health.health?.backup_encryption_configured ? "Configured" : "Not configured" },
    { title: "Offsite destination", ok: Boolean(health.health?.offsite_backup_configured), detail: offsiteDetail },
    { title: "Running API release", ok: Boolean(health.health?.release_verified), detail: health.health?.release_verified ? "SHA matches deployment marker" : "Release identity not verified" },
    { title: "Deployment storage", ok: disks.length > 0 && disks.every((disk) => disk.deployment_space_ok), detail: disks.length ? `${disks.length} filesystem(s) checked` : "Capacity unavailable" },
  ];
  const passed = checks.filter((check) => check.ok).length;
  const configReady = health.ok && passed === checks.length;

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page system-page">
        <header className="page-header system-hero">
          <div><span className="eyebrow">Readiness</span><h1>Launch and production readiness</h1><p className="muted">Configuration and operational checks based on live evidence. A healthy configuration does not certify disaster recovery.</p></div>
          <div className="action-row"><StatusBadge label={configReady ? "configuration checked" : "needs attention"} tone={configReady ? "ok" : "warning"} /><Link className="button ghost" href="/controls/production-health">Full health details</Link></div>
        </header>

        <section className="system-health-grid">
          <div className="system-health-card"><span>API</span><strong>{health.ok ? "Online" : "Issue"}</strong><small>Current backend response</small></div>
          <div className="system-health-card"><span>Checks passed</span><strong>{passed}/{checks.length}</strong><small>Configuration checks, not recovery certification</small></div>
          <div className="system-health-card"><span>Backups</span><strong>{health.health?.backup_count || 0}</strong><small>Server-visible copies</small></div>
          <div className="system-health-card"><span>Payroll runs</span><strong>{history ? history.total : "Unavailable"}</strong><small>Full payroll history total</small></div>
        </section>

        <section className="system-panel"><header><div><h2>Production checklist</h2><p>Configuration checks use live health evidence; total payroll-run count uses the paginated history endpoint. Offsite copy integrity and restore drills require separate verification.</p></div><StatusBadge label={configReady ? "configuration complete" : `${checks.length - passed} need attention`} tone={configReady ? "ok" : "warning"} /></header><div className="system-panel-body system-check-list">{checks.map((check) => <div className="system-check-row" key={check.title}><strong>{check.title}</strong><p>{check.detail}</p><StatusBadge label={check.ok ? "OK" : "Needed"} tone={check.ok ? "ok" : "warning"} /></div>)}</div></section>

        <section className="system-panel"><header><div><h2>Operational verification</h2><p>Open the canonical workspaces rather than duplicating controls here.</p></div></header><div className="system-panel-body system-catalog"><Link className="system-link-card" href="/backup"><strong>Backups</strong><span>Create, verify, and download recovery files.</span></Link><Link className="system-link-card" href="/settings"><strong>Settings</strong><span>Review backend and database status.</span></Link><Link className="system-link-card" href="/payroll/runs"><strong>Payroll runs</strong><span>Review lifecycle and immutable paid history.</span></Link>{latestRun ? <Link className="system-link-card" href={`/payroll/runs/${latestRun.id}/audit`}><strong>Latest audit</strong><span>Inspect the newest run timeline.</span></Link> : null}</div></section>
      </div>
    </Shell>
  );
}
