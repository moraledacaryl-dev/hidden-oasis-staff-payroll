import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { currentSession } from "@/lib/session";

export default async function OldSchedulesPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Old schedules</span>
            <h1>Old schedule backfill</h1>
            <p className="muted">Use this for old payroll periods where scheduled time should count as actual worked time.</p>
          </div>
          <StatusBadge label="admin" tone="warning" />
        </header>

        <section className="card">
          <div className="panel-title"><h2>What this does</h2></div>
          <p className="muted">This reads the old schedules table and creates approved time logs only for employee/date rows that do not already have a non-rejected time log. It skips rest days and invalid rows.</p>
        </section>

        <section className="card">
          <div className="panel-title"><h2>Run from server</h2></div>
          <div className="copy-box">python3 scripts/backfill_legacy_schedule_time_logs.py --all --dry-run</div>
          <div className="copy-box">python3 scripts/backfill_legacy_schedule_time_logs.py --all</div>
          <p className="muted">Dry run first, then run the actual command after checking the insert count.</p>
        </section>

        <section className="card">
          <div className="action-row">
            <Link className="primary-link" href="/controls">Back to Controls</Link>
            <Link className="primary-link" href="/schedule">Open Schedule</Link>
            <Link className="primary-link" href="/payroll/runs">Open Payroll Runs</Link>
          </div>
        </section>
      </div>
    </Shell>
  );
}
