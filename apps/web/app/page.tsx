import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getEmployees, getMeta, getPayrollPreview, peso } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function CommandCenterPage() {
  const [meta, employees, preview] = await Promise.all([
    getMeta(),
    getEmployees(),
    getPayrollPreview(DEFAULT_START, DEFAULT_END),
  ]);

  const activeEmployees = employees.filter((employee) => employee.status !== "Inactive" && employee.status !== "Terminated").length;
  const blockers = preview.checks.filter((check) => check.severity === "Blocker").length;
  const warnings = preview.checks.filter((check) => check.severity === "Warning").length;

  return (
    <Shell role="owner">
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Production Migration · Web Shell</span>
            <h1>Staff payroll command center</h1>
            <p className="muted">
              This is the Next.js interface connected to the FastAPI wrapper. Payroll values are still computed by the existing Python engine.
            </p>
          </div>
          <div className="badge-row">
            <StatusBadge label="API connected" />
            <StatusBadge label={preview.mode} tone="warning" />
          </div>
        </header>

        <section className="grid cols-4">
          <MetricCard label="Employees" value={activeEmployees} detail={`${meta.employee_count} total records`} />
          <MetricCard label="Gross preview" value={peso(preview.totals.gross_pay)} detail={`${DEFAULT_START} to ${DEFAULT_END}`} />
          <MetricCard label="Net preview" value={peso(preview.totals.net_pay)} detail="Preview only, not saved" />
          <MetricCard label="Cash advance deduction" value={peso(preview.totals.cash_advance_deduction)} detail="From existing payroll engine" />
        </section>

        <section className="grid cols-2">
          <div className="card">
            <div className="panel-title">
              <div>
                <h2>Cutoff readiness</h2>
                <p className="muted">QA from the existing payroll preflight checker.</p>
              </div>
              <div className="badge-row">
                <StatusBadge label={`${blockers} blockers`} tone={blockers ? "danger" : "ok"} />
                <StatusBadge label={`${warnings} warnings`} tone={warnings ? "warning" : "ok"} />
              </div>
            </div>
            <div className="action-list">
              {preview.checks.slice(0, 5).map((check, index) => (
                <div className="action-item" key={`${check.category}-${index}`}>
                  <strong>{check.category}</strong>
                  <p>{check.issue}</p>
                  <p className="muted">{check.recommended_action}</p>
                </div>
              ))}
              {preview.checks.length === 0 ? <p className="muted">No blockers or warnings detected.</p> : null}
            </div>
          </div>

          <div className="card">
            <div className="panel-title">
              <div>
                <h2>Migration safety</h2>
                <p className="muted">Do-not-break controls for this stage.</p>
              </div>
              <StatusBadge label="safe stage" />
            </div>
            <div className="action-list">
              <div className="action-item"><strong>Streamlit remains fallback.</strong><p className="muted">The current app is not deleted or replaced.</p></div>
              <div className="action-item"><strong>SQLite remains source database.</strong><p className="muted">PostgreSQL migration happens later only after comparison.</p></div>
              <div className="action-item"><strong>Payroll formulas stay in Python.</strong><p className="muted">Next.js calls the API and does not calculate payroll.</p></div>
              <div className="action-item"><strong>Write actions disabled.</strong><p className="muted">Preview is read-only until totals match the Streamlit app.</p></div>
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
