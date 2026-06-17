import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews, getEmployees, getMeta, getPayrollPreview, peso } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";
import type { AttendanceException, AttendanceReview } from "@/lib/api";
import type { PayrollPreview } from "@/lib/types";

export default async function CommandCenterPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }
  const { periodStart, periodEnd } = currentCutoff();
  const canSeePayroll = session.role_key === "owner" || session.role_key === "payroll";
  const [meta, employees] = await Promise.all([getMeta(), getEmployees()]);
  let preview: PayrollPreview | null = null;
  let exceptions: AttendanceException[] = [];
  let reviews: AttendanceReview[] = [];
  if (canSeePayroll) {
    preview = await getPayrollPreview(periodStart, periodEnd);
  } else {
    [exceptions, reviews] = await Promise.all([
      getAttendanceExceptions(periodStart, periodEnd),
      getAttendanceReviews(periodStart, periodEnd),
    ]);
  }
  const activeEmployees = employees.filter((employee) => employee.status !== "Inactive" && employee.status !== "Terminated").length;
  const blockers = preview?.checks.filter((check) => check.severity === "Blocker").length || 0;
  const warnings = preview?.checks.filter((check) => check.severity === "Warning").length || 0;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Command Center</span>
            <h1>Staff Payroll</h1>
            <p className="muted">{periodStart} to {periodEnd}</p>
          </div>
          <div className="badge-row"><StatusBadge label="API connected" />{preview ? <StatusBadge label={preview.mode} tone="warning" /> : <StatusBadge label="attendance view" tone="warning" />}</div>
        </header>
        <section className="grid cols-4">
          <MetricCard label="Employees" value={activeEmployees} detail={`${meta.employee_count} total records`} />
          {preview ? <MetricCard label="Gross" value={peso(preview.totals.gross_pay)} detail="Preview" /> : <MetricCard label="Exceptions" value={exceptions.length} detail="Open" />}
          {preview ? <MetricCard label="Net" value={peso(preview.totals.net_pay)} detail="Preview" /> : <MetricCard label="Reviews" value={reviews.length} detail="Recorded" />}
          {preview ? <MetricCard label="Cash advances" value={peso(preview.totals.cash_advance_deduction)} detail="Deductions" /> : <MetricCard label="Role" value="Supervisor" detail="No payroll totals" />}
        </section>
        <section className="grid cols-2">
          <div className="card">
            <div className="panel-title"><div><h2>Cutoff readiness</h2><p className="muted">Items to clear before approval.</p></div><div className="badge-row"><StatusBadge label={`${blockers} blockers`} tone={blockers ? "danger" : "ok"} /><StatusBadge label={`${warnings} warnings`} tone={warnings ? "warning" : "ok"} /></div></div>
            <div className="action-list">{preview ? preview.checks.slice(0, 5).map((check, index) => (<div className="action-item" key={`${check.category}-${index}`}><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>)) : exceptions.slice(0, 5).map((item) => (<div className="action-item" key={item.id}><strong>{item.full_name}</strong><p>{item.work_date} · {item.attendance_status}</p></div>))}{preview?.checks.length === 0 || (!preview && exceptions.length === 0) ? <p className="muted">No open items.</p> : null}</div>
          </div>
          <div className="card">
            <div className="panel-title"><div><h2>Guardrails</h2><p className="muted">Production rules.</p></div><StatusBadge label="active" /></div>
            <div className="action-list"><div className="action-item"><strong>Python payroll engine</strong><p className="muted">Python calculates pay.</p></div><div className="action-item"><strong>SQLite source</strong><p className="muted">Database files stay out of Git.</p></div><div className="action-item"><strong>Role-gated writes</strong><p className="muted">Backend permissions are required.</p></div><div className="action-item"><strong>Backup first</strong><p className="muted">Run a backup before migrations.</p></div></div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
