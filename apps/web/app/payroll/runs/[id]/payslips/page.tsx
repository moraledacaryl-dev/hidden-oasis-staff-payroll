import { Shell } from "@/components/Shell";
import { getPayrollRunReview, peso } from "@/lib/api";

function govTax(item: { sss_ee: number; philhealth_ee: number; pagibig_ee: number; tax: number }) {
  return Number(item.sss_ee || 0) + Number(item.philhealth_ee || 0) + Number(item.pagibig_ee || 0) + Number(item.tax || 0);
}

export default async function PayslipPreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const review = await getPayrollRunReview(Number(id));
  const run = review.run;
  const items = review.items;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payslip Preview</span><h1>Run #{run.id} · {run.period_start} to {run.period_end}</h1><p className="muted">Printable preview only. Payroll is not marked paid from this page.</p></div></header>
        <section className="grid cols-2">{items.map((item) => (<article className="card" key={item.id}><div className="panel-title"><div><h2>{item.employee_name}</h2><p className="muted">{item.department}</p></div><strong>{peso(item.net_pay)}</strong></div><div className="grid cols-2"><div><p className="muted">Earnings</p><p>Regular: {peso(item.regular_pay)}</p><p>OT: {peso(item.ot_pay)}</p><p>Night diff: {peso(item.night_diff_pay)}</p><p>Holiday: {peso(item.holiday_pay)}</p><p>Other: {peso((item.paid_leave_pay || 0) + (item.freelance_pay || 0) + (item.other_earnings || 0))}</p></div><div><p className="muted">Deductions</p><p>Gov/tax: {peso(govTax(item))}</p><p>Cash advance: {peso(item.cash_advance_deduction)}</p><p>Other: {peso(item.other_deductions)}</p><p>Total: {peso(item.total_deductions)}</p></div></div><hr /><div className="panel-title"><span>Gross {peso(item.gross_pay)}</span><strong>Net {peso(item.net_pay)}</strong></div></article>))}</section>
      </div>
    </Shell>
  );
}
