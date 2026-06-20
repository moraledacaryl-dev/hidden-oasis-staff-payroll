import Link from "next/link";
import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews, getEmployees, getMeta, getPayrollPreview, peso } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";
import type { AttendanceException, AttendanceReview } from "@/lib/api";
import type { PayrollPreview } from "@/lib/types";

export default async function DashboardPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;

  const { periodStart, periodEnd } = currentCutoff();
  const canSeePayroll = session.role_key === "owner" || session.role_key === "payroll";
  const [meta, employees] = await Promise.all([getMeta(), getEmployees()]);
  let preview: PayrollPreview | null = null;
  let exceptions: AttendanceException[] = [];
  let reviews: AttendanceReview[] = [];

  if (canSeePayroll) preview = await getPayrollPreview(periodStart, periodEnd);
  else [exceptions, reviews] = await Promise.all([getAttendanceExceptions(periodStart, periodEnd), getAttendanceReviews(periodStart, periodEnd)]);

  const activeEmployees = employees.filter((employee) => employee.status !== "Inactive" && employee.status !== "Terminated").length;
  const blockers = preview?.checks.filter((check) => check.severity === "Blocker").length || 0;
  const warnings = preview?.checks.filter((check) => check.severity === "Warning").length || 0;
  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const otPending = exceptions.filter((item) => item.ot_status === "Pending").length;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Dashboard</span><h1>{canSeePayroll ? "Payroll overview" : "Supervisor overview"}</h1><p className="muted">{periodStart} to {periodEnd}</p></div>
          <div className="badge-row"><StatusBadge label="Connected" />{preview ? <StatusBadge label={preview.mode} tone="warning" /> : <StatusBadge label="Operations" tone="warning" />}</div>
        </header>

        <section className="grid cols-4">
          <MetricCard label="Active Staff" value={activeEmployees} detail={`${meta.employee_count} records`} />
          {preview ? <MetricCard label="Gross" value={peso(preview.totals.gross_pay)} detail="Preview" /> : <MetricCard label="Open Issues" value={exceptions.length} detail="Attendance" />}
          {preview ? <MetricCard label="Net" value={peso(preview.totals.net_pay)} detail="Preview" /> : <MetricCard label="Missing Logs" value={missing} detail="Time in/out" />}
          {preview ? <MetricCard label="Deductions" value={peso(preview.totals.total_deductions)} detail="Preview" /> : <MetricCard label="OT Pending" value={otPending} detail={`${absent} absent`} />}
        </section>

        <section className="grid cols-2">
          <div className="card">
            <div className="panel-title"><div><h2>{canSeePayroll ? "Cutoff readiness" : "Action list"}</h2><p className="muted">{canSeePayroll ? "Items to clear before approval." : "Attendance items requiring review."}</p></div>{canSeePayroll ? <div className="badge-row"><StatusBadge label={`${blockers} blockers`} tone={blockers ? "danger" : "ok"} /><StatusBadge label={`${warnings} warnings`} tone={warnings ? "warning" : "ok"} /></div> : <StatusBadge label={`${reviews.length} reviewed`} />}</div>
            <div className="action-list">{preview ? preview.checks.slice(0, 5).map((check, index) => <div className="action-item" key={`${check.category}-${index}`}><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>) : exceptions.slice(0, 5).map((item) => <div className="action-item" key={item.id}><strong>{item.full_name}</strong><p>{item.work_date} · {item.attendance_status}</p><p className="muted">{item.actual_in || "—"} / {item.actual_out || "—"}</p></div>)}{preview?.checks.length === 0 || (!preview && exceptions.length === 0) ? <p className="muted">No open items.</p> : null}</div>
          </div>

          <div className="card">
            <div className="panel-title"><div><h2>Quick actions</h2><p className="muted">Common work areas.</p></div></div>
            <div className="grid cols-2">
                <Link className="primary-link" href="/schedule">Schedule</Link>
                <Link className="primary-link" href="/attendance">Attendance</Link>
                {session.role_key === "supervisor" ? <Link className="primary-link" href="/performance-reviews">Performance Reviews</Link> : <Link className="primary-link" href="/payroll/runs">Payroll Runs</Link>}
                {session.role_key === "supervisor" ? <Link className="primary-link" href="/cash-advances">Cash Advances</Link> : <Link className="primary-link" href="/hr">HR Records</Link>}
                <Link className="primary-link" href={session.role_key === "supervisor" ? "/reports/operations" : "/reports"}>Reports</Link>
                <Link className="primary-link" href="/settings/password">Account</Link>
              </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
