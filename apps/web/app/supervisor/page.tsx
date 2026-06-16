import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollPreview } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function SupervisorPage() {
  const preview = await getPayrollPreview(DEFAULT_START, DEFAULT_END);
  const attendanceChecks = preview.checks.filter((check) => check.category === "Attendance" || check.category === "Overtime" || check.category === "Leaves");

  return (
    <Shell role="supervisor">
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Supervisor</span>
            <h1>Daily action queue</h1>
            <p className="muted">This first web shell surfaces the work supervisors must clear before payroll can be approved.</p>
          </div>
          <StatusBadge label="review only" tone="warning" />
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>Attendance exceptions</strong><p className="muted">Resolve missing, pending, disputed, or incomplete logs before cutoff approval.</p></div>
          <div className="card"><strong>OT decisions</strong><p className="muted">Approve or reject OT with reason. Payroll should only pay approved OT.</p></div>
          <div className="card"><strong>Leave classifications</strong><p className="muted">Approve/reject pending leave and classify paid versus unpaid impact.</p></div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Current cutoff items</h2>
              <p className="muted">Pulled from payroll QA for {DEFAULT_START} to {DEFAULT_END}.</p>
            </div>
          </div>
          <div className="action-list">
            {attendanceChecks.map((check, index) => (
              <div className="action-item" key={`${check.category}-${index}`}>
                <div className="badge-row"><StatusBadge label={check.severity} tone={check.severity === "Blocker" ? "danger" : "warning"} /></div>
                <strong>{check.category}</strong>
                <p>{check.issue}</p>
                <p className="muted">{check.recommended_action}</p>
              </div>
            ))}
            {attendanceChecks.length === 0 ? <p className="muted">No attendance, OT, or leave QA items for this cutoff.</p> : null}
          </div>
        </section>
      </div>
    </Shell>
  );
}
