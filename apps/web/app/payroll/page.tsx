import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge, severityTone } from "@/components/StatusBadge";
import { getPayrollPreview, numberText, peso } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function PayrollPage() {
  const preview = await getPayrollPreview(DEFAULT_START, DEFAULT_END);

  return (
    <Shell role="owner">
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payroll</span>
            <h1>Cutoff preview</h1>
            <p className="muted">Preview only. Saving, approval, paid, lock, and reopen stay disabled until comparison with Streamlit is verified.</p>
          </div>
          <div className="badge-row">
            <StatusBadge label={`${DEFAULT_START} to ${DEFAULT_END}`} tone="warning" />
            <StatusBadge label={preview.mode} tone="warning" />
          </div>
        </header>

        <section className="grid cols-4">
          <MetricCard label="Employees" value={preview.totals.employees} />
          <MetricCard label="Gross pay" value={peso(preview.totals.gross_pay)} />
          <MetricCard label="Total deductions" value={peso(preview.totals.total_deductions)} />
          <MetricCard label="Net pay" value={peso(preview.totals.net_pay)} />
        </section>

        <section className="grid cols-2">
          <div className="card">
            <div className="panel-title">
              <div>
                <h2>QA checks</h2>
                <p className="muted">From the existing `core/quality.py` checker.</p>
              </div>
              <StatusBadge label={preview.summary} tone={preview.checks.some((c) => c.severity === "Blocker") ? "danger" : "warning"} />
            </div>
            <div className="action-list">
              {preview.checks.map((check, index) => (
                <div className="action-item" key={`${check.category}-${index}`}>
                  <div className="badge-row"><StatusBadge label={check.severity} tone={severityTone(check.severity)} /></div>
                  <strong>{check.category}</strong>
                  <p>{check.issue}</p>
                  <p className="muted">{check.recommended_action}</p>
                </div>
              ))}
              {preview.checks.length === 0 ? <p className="muted">No QA checks returned.</p> : null}
            </div>
          </div>

          <div className="card">
            <div className="panel-title">
              <div>
                <h2>Payroll controls</h2>
                <p className="muted">Intentionally disabled during first web migration stage.</p>
              </div>
            </div>
            <div className="action-list">
              <div className="action-item"><strong>Save draft</strong><p className="muted">Blocked until preview totals match Streamlit.</p></div>
              <div className="action-item"><strong>Approve payroll</strong><p className="muted">Blocked until write endpoints and server-side permission checks are added.</p></div>
              <div className="action-item"><strong>Mark paid / lock</strong><p className="muted">Blocked until reconciliation and audit behavior are tested.</p></div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Employee preview lines</h2>
              <p className="muted">Computed by the existing Python payroll engine through FastAPI.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Regular hrs</th>
                  <th>OT hrs</th>
                  <th>ND hrs</th>
                  <th>Gross</th>
                  <th>Deductions</th>
                  <th>CA deduction</th>
                  <th>Net</th>
                  <th>Warnings</th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((item) => (
                  <tr key={item.employee_id}>
                    <td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code}</span></td>
                    <td>{numberText(item.regular_hours)}</td>
                    <td>{numberText(item.approved_ot_hours)}</td>
                    <td>{numberText(item.night_diff_hours)}</td>
                    <td>{peso(item.gross_pay)}</td>
                    <td>{peso(item.total_deductions)}</td>
                    <td>{peso(item.cash_advance_deduction)}</td>
                    <td><strong>{peso(item.net_pay)}</strong></td>
                    <td>{item.warnings?.length ? `${item.warnings.length} warning(s)` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
