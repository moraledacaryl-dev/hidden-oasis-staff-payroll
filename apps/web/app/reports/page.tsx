import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { getPayrollPreview, peso } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";

export default async function ReportsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  const { periodStart, periodEnd } = currentCutoff();
  const preview = await getPayrollPreview(periodStart, periodEnd);
  const contributions = preview.items.reduce((totals, item) => ({
    sss: totals.sss + Number(item.sss_ee || 0) + Number(item.sss_er || 0) + Number(item.sss_ec || 0),
    philhealth: totals.philhealth + Number(item.philhealth_ee || 0) + Number(item.philhealth_er || 0),
    pagibig: totals.pagibig + Number(item.pagibig_ee || 0) + Number(item.pagibig_er || 0),
    tax: totals.tax + Number(item.tax || 0),
    cashAdvances: totals.cashAdvances + Number(item.cash_advance_deduction || 0),
  }), { sss: 0, philhealth: 0, pagibig: 0, tax: 0, cashAdvances: 0 });

  return <Shell allowedRoles={["owner", "payroll"]}><div className="page report-page">
    <header className="report-hero"><div><span className="eyebrow">Reports</span><h1>Payroll reports</h1><p className="muted">Current cutoff reporting for {periodStart} to {periodEnd}.</p></div><div className="report-actions"><Link className="button ghost" href="/payroll/runs">Payroll runs</Link><Link className="button" href="/payslips">Payslips</Link></div></header>
    <section className="report-kpis"><div className="report-kpi"><span>Employees</span><strong>{preview.totals.employees}</strong><small>In current preview</small></div><div className="report-kpi"><span>Gross payroll</span><strong>{peso(preview.totals.gross_pay)}</strong><small>Before deductions</small></div><div className="report-kpi"><span>Total deductions</span><strong>{peso(preview.totals.total_deductions)}</strong><small>Employee deductions</small></div><div className="report-kpi"><span>Net payroll</span><strong>{peso(preview.totals.net_pay)}</strong><small>Expected payout</small></div></section>
    <section className="report-grid">
      <article className="report-panel"><header><div><h2>Report catalog</h2><p>Open the operational source used for each report.</p></div></header><div className="report-panel-body report-catalog"><Link className="report-link" href="/payroll"><div><strong>Payroll preview</strong><small>Employee earnings, deductions, and checks</small></div><span>Open</span></Link><Link className="report-link" href="/payroll/runs"><div><strong>Payroll run history</strong><small>Saved, approved, paid, and revised runs</small></div><span>Open</span></Link><Link className="report-link" href="/payslips"><div><strong>Payslip distribution</strong><small>Latest active payroll version by period</small></div><span>Open</span></Link><Link className="report-link" href="/cash-advances"><div><strong>Cash advance balances</strong><small>Outstanding balances and repayments</small></div><span>Open</span></Link></div></article>
      <article className="report-panel"><header><div><h2>Remittances and deductions</h2><p>Calculated from the current payroll preview.</p></div></header><div className="report-panel-body report-remittance"><div><span>SSS</span><strong>{peso(contributions.sss)}</strong></div><div><span>PhilHealth</span><strong>{peso(contributions.philhealth)}</strong></div><div><span>Pag-IBIG</span><strong>{peso(contributions.pagibig)}</strong></div><div><span>Withholding tax</span><strong>{peso(contributions.tax)}</strong></div><div><span>Cash advances</span><strong>{peso(contributions.cashAdvances)}</strong></div></div></article>
    </section>
  </div></Shell>;
}
