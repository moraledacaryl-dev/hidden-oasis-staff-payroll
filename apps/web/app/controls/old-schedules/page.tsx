import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { currentSession } from "@/lib/session";

const migrations = [
  {
    title: "Make legacy schedules editable",
    description: "Copies legacy schedule rows into scheduled_shifts, the editable source used by the weekly calendar and employee-day drawer. Existing equivalent rows are skipped.",
    preview: "python3 scripts/migrate_legacy_schedules_to_scheduled_shifts.py --all",
    apply: "python3 scripts/migrate_legacy_schedules_to_scheduled_shifts.py --all --apply",
  },
  {
    title: "Backfill legacy schedules as actual attendance",
    description: "Creates approved time logs only where old scheduled time is intended to count as actual worked time. This is separate from making the schedule editable.",
    preview: "python3 scripts/backfill_legacy_schedule_time_logs.py --all --dry-run",
    apply: "python3 scripts/backfill_legacy_schedule_time_logs.py --all",
  },
];

export default async function OldSchedulesPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page system-page">
        <header className="page-header system-hero"><div><span className="eyebrow">Legacy controls</span><h1>Old schedule migration tools</h1><p className="muted">These are administrative terminal procedures for historical records. They do not replace the current Schedule and Attendance workspaces.</p></div><StatusBadge label="restricted" tone="warning" /></header>

        <div className="legacy-warning"><strong>Run preview first.</strong> Review the reported counts and database target before using an apply command. Keep a verified backup before changing historical schedule or attendance records.</div>

        <section className="system-grid">{migrations.map((migration) => <article className="system-panel" key={migration.title}><header><div><h2>{migration.title}</h2><p>{migration.description}</p></div></header><div className="system-panel-body"><div className="grid"><div><span className="eyebrow">1 · Preview</span><div className="legacy-command">{migration.preview}</div></div><div><span className="eyebrow">2 · Apply after review</span><div className="legacy-command">{migration.apply}</div></div></div></div></article>)}</section>

        <section className="system-panel"><header><div><h2>Canonical workspaces</h2><p>Return to the live interfaces after any approved migration.</p></div></header><div className="system-panel-body system-catalog"><Link className="system-link-card" href="/controls"><strong>System controls</strong><span>Return to the central controls workspace.</span></Link><Link className="system-link-card" href="/schedule"><strong>Weekly schedule</strong><span>Review editable planned shifts.</span></Link><Link className="system-link-card" href="/attendance/review"><strong>Attendance review</strong><span>Review actual attendance and exceptions.</span></Link><Link className="system-link-card" href="/payroll/runs"><strong>Payroll runs</strong><span>Confirm historical payroll remains consistent.</span></Link></div></section>
      </div>
    </Shell>
  );
}
