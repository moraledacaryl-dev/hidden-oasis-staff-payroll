import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getEmployees, getMeta, getPayrollPreview, peso } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function CommandCenterPage() {
  const [meta, employees, preview] = await Promise.all([getMeta(), getEmployees(), getPayrollPreview(DEFAULT_START, DEFAULT_END)]);
  const activeEmployees = employees.filter((employee) => employee.status !== "Inactive" && employee.status !== "Terminated").length;
  const blockers = preview.checks.filter((check) => check.severity === "Blocker").length;
  const warnings = preview.checks.filter((check) => check.severity === "Warning").length;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Command Center</span>
            <h1>Staff Payroll</h1>
            <p className="muted">Payroll status, staff count, and cutoff checks.</p>
          </div>
          <div className="badge-row"><StatusBadge label="API connected" /><StatusBadge label={preview.mode} tone="warning" /></div>
        </header>
        <section className="grid cols-4">
          <MetricCard label="Employees" value={activeEmployees} detail={`${meta.employee_count} total records`} />
          <MetricCard label="Gross" value={peso(preview.totals.gross_pay)} detail={`${DEFAULT_START} to ${DEFAULT_END}`} />
          <MetricCard label="Net" value={peso(preview.totals.net_pay)} detail="Current preview" />
          <MetricCard label="Cash advances" value={peso(preview.totals.cash_advance_deduction)} detail="Deductions" />
        </section>
        <section className="grid cols-2">
          <div className="card">
            <div className="panel-title"><div><h2>Cutoff readiness</h2><p className="muted">Items to clear before approval.</p></div><div className="badge-row"><StatusBadge label={`${blockers} blockers`} tone={blockers ? "danger" : "ok"} /><StatusBadge label={`${warnings} warnings`} tone={warnings ? "warning" : "ok"} /></div></div>
            <div className="action-list">{preview.checks.slice(0, 5).map((check, index) => (<div className="action-item" key={`${check.category}-${index}`}><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>))}{preview.checks.length === 0 ? <p className="muted">No blockers or warnings detected.</p> : null}</div>
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
