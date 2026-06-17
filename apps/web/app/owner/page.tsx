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
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Owner</span><h1>Approval cockpit</h1><p className="muted">Review payout and blockers.</p></div><StatusBadge label={blockers ? "not ready" : "review ready"} tone={blockers ? "danger" : "warning"} /></header>
        <section className="grid cols-4"><MetricCard label="Net payout" value={peso(preview.totals.net_pay)} detail="Cash to release if approved" /><MetricCard label="Gross payroll" value={peso(preview.totals.gross_pay)} /><MetricCard label="Deductions" value={peso(preview.totals.total_deductions)} /><MetricCard label="Cash advance collected" value={peso(preview.totals.cash_advance_deduction)} /></section>
        <section className="card"><div className="panel-title"><div><h2>Decision gates</h2><p className="muted">Approve only when clean.</p></div></div><div className="grid cols-3"><div className="action-item"><strong>1. Blockers</strong><p className="muted">Must be zero.</p></div><div className="action-item"><strong>2. Cash</strong><p className="muted">Net payout must be funded.</p></div><div className="action-item"><strong>3. Approval</strong><p className="muted">Use saved payroll runs.</p></div></div></section>
      </div>
    </Shell>
  );
}
