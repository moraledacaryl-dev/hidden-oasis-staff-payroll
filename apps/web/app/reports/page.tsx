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
  const contributions = preview.items.reduce(
    (totals, item) => ({
      sss: totals.sss + Number(item.sss_ee || 0) + Number(item.sss_er || 0) + Number(item.sss_ec || 0),
      philhealth: totals.philhealth + Number(item.philhealth_ee || 0) + Number(item.philhealth_er || 0),
      pagibig: totals.pagibig + Number(item.pagibig_ee || 0) + Number(item.pagibig_er || 0),
      tax: totals.tax + Number(item.tax || 0),
      cashAdvances: totals.cashAdvances + Number(item.cash_advance_deduction || 0),
    }),
    { sss: 0, philhealth: 0, pagibig: 0, tax: 0, cashAdvances: 0 },
  );

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Reports</span><h1>Payroll reports</h1><p className="muted">{periodStart} to {periodEnd}</p></div></header>
        <section className="grid cols-4"><MetricCard label="Employees in preview" value={preview.totals.employees} /><MetricCard label="Gross" value={peso(preview.totals.gross_pay)} /><MetricCard label="Deductions" value={peso(preview.totals.total_deductions)} /><MetricCard label="Net" value={peso(preview.totals.net_pay)} /></section>
        <section className="card">
          <div className="panel-title"><h2>Remittances and deductions</h2></div>
          <div className="grid cols-3">
            <div className="action-item"><strong>SSS</strong><p>{peso(contributions.sss)}</p></div>
            <div className="action-item"><strong>PhilHealth</strong><p>{peso(contributions.philhealth)}</p></div>
            <div className="action-item"><strong>Pag-IBIG</strong><p>{peso(contributions.pagibig)}</p></div>
            <div className="action-item"><strong>Withholding tax</strong><p>{peso(contributions.tax)}</p></div>
            <div className="action-item"><strong>Cash advance deductions</strong><p>{peso(contributions.cashAdvances)}</p></div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
