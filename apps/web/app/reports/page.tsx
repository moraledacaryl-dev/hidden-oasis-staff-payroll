import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { getPayrollPreview, peso } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";

export default async function ReportsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const { periodStart, periodEnd } = currentCutoff();
  const preview = await getPayrollPreview(periodStart, periodEnd);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Reports</span><h1>Payroll reports</h1><p className="muted">{periodStart} to {periodEnd}</p></div></header>
        <section className="grid cols-4"><MetricCard label="Employees in preview" value={preview.totals.employees} /><MetricCard label="Gross" value={peso(preview.totals.gross_pay)} /><MetricCard label="Deductions" value={peso(preview.totals.total_deductions)} /><MetricCard label="Net" value={peso(preview.totals.net_pay)} /></section>
        <section className="card"><div className="panel-title"><div><h2>Next reports</h2><p className="muted">Planned summaries.</p></div></div><div className="grid cols-3"><div className="action-item"><strong>Labor by department</strong><p className="muted">Department totals.</p></div><div className="action-item"><strong>Cash advances</strong><p className="muted">Open balances.</p></div><div className="action-item"><strong>Contributions</strong><p className="muted">SSS, PhilHealth, Pag-IBIG.</p></div></div></section>
      </div>
    </Shell>
  );
}
