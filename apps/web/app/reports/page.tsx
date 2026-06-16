import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { getPayrollPreview, peso } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function ReportsPage() {
  const preview = await getPayrollPreview(DEFAULT_START, DEFAULT_END);

  return (
    <Shell role="owner">
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Reports</span>
            <h1>Payroll report foundation</h1>
            <p className="muted">First production report view. CSV/PDF exports remain in the existing app until API write/export endpoints are added.</p>
          </div>
        </header>

        <section className="grid cols-4">
          <MetricCard label="Employees in preview" value={preview.totals.employees} />
          <MetricCard label="Gross" value={peso(preview.totals.gross_pay)} />
          <MetricCard label="Deductions" value={peso(preview.totals.total_deductions)} />
          <MetricCard label="Net" value={peso(preview.totals.net_pay)} />
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Report roadmap</h2>
              <p className="muted">These should be API-backed after write endpoints are verified.</p>
            </div>
          </div>
          <div className="grid cols-3">
            <div className="action-item"><strong>Labor cost by department</strong><p className="muted">Needs department grouping endpoint.</p></div>
            <div className="action-item"><strong>Cash advance exposure</strong><p className="muted">Needs receivable aging endpoint.</p></div>
            <div className="action-item"><strong>Contribution review</strong><p className="muted">Needs validated SSS/PhilHealth/Pag-IBIG basis report.</p></div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
