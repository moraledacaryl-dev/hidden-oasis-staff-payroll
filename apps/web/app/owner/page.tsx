import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollPreview, peso } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function OwnerPage() {
  const preview = await getPayrollPreview(DEFAULT_START, DEFAULT_END);
  const blockers = preview.checks.filter((check) => check.severity === "Blocker").length;

  return (
    <Shell role="owner">
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Owner</span>
            <h1>Approval cockpit</h1>
            <p className="muted">Owner view for deciding whether payroll is financially and operationally ready.</p>
          </div>
          <StatusBadge label={blockers ? "not ready" : "review ready"} tone={blockers ? "danger" : "warning"} />
        </header>

        <section className="grid cols-4">
          <MetricCard label="Net payout" value={peso(preview.totals.net_pay)} detail="Cash to release if approved" />
          <MetricCard label="Gross payroll" value={peso(preview.totals.gross_pay)} />
          <MetricCard label="Deductions" value={peso(preview.totals.total_deductions)} />
          <MetricCard label="Cash advance collected" value={peso(preview.totals.cash_advance_deduction)} />
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Owner decision gates</h2>
              <p className="muted">Write actions will be added later after preview verification.</p>
            </div>
          </div>
          <div className="grid cols-3">
            <div className="action-item"><strong>1. Check blockers</strong><p className="muted">Payroll cannot be approved while blocker QA items remain.</p></div>
            <div className="action-item"><strong>2. Confirm cash</strong><p className="muted">Net payout should match available cash/bank release plan.</p></div>
            <div className="action-item"><strong>3. Approve only after compare</strong><p className="muted">Compare this web preview with Streamlit before adding approval writes.</p></div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
