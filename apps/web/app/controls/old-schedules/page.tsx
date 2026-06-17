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
            <h1>Old schedule tools</h1>
            <p className="muted">Use this for old schedule records that still come from the legacy schedules table.</p>
          </div>
          <StatusBadge label="admin" tone="warning" />
        </header>

        <section className="card">
          <div className="panel-title"><h2>Make old schedules editable</h2></div>
          <p className="muted">This copies legacy schedule rows into scheduled_shifts, which is the editable table used by the drag-and-drop calendar and day editor. It skips rows that were already migrated or already exist with the same employee, date, start time, and end time.</p>
          <div className="copy-box">python3 scripts/migrate_legacy_schedules_to_scheduled_shifts.py --all</div>
          <div className="copy-box">python3 scripts/migrate_legacy_schedules_to_scheduled_shifts.py --all --apply</div>
          <p className="muted">Run the first command to preview. Run the second command only after checking the would_insert count.</p>
        </section>

        <section className="card">
          <div className="panel-title"><h2>Treat old schedules as actual attendance</h2></div>
          <p className="muted">This is separate. It creates approved time logs from old schedules for payroll calculations where scheduled time should count as actual worked time.</p>
          <div className="copy-box">python3 scripts/backfill_legacy_schedule_time_logs.py --all --dry-run</div>
          <div className="copy-box">python3 scripts/backfill_legacy_schedule_time_logs.py --all</div>
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
