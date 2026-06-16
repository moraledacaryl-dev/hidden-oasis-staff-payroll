import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { getPayrollRunReview, peso } from "@/lib/api";

function benefitsTotal(item: { sss_er: number; sss_ec: number; philhealth_er: number; pagibig_er: number }) {
  return Number(item.sss_er || 0) + Number(item.sss_ec || 0) + Number(item.philhealth_er || 0) + Number(item.pagibig_er || 0);
}

function mandatoryDeductions(item: { sss_ee: number; philhealth_ee: number; pagibig_ee: number }) {
  return Number(item.sss_ee || 0) + Number(item.philhealth_ee || 0) + Number(item.pagibig_ee || 0);
}

function taxAndOther(item: { tax: number; cash_advance_deduction: number; other_deductions: number }) {
  return Number(item.tax || 0) + Number(item.cash_advance_deduction || 0) + Number(item.other_deductions || 0);
}

export default async function PayslipPreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const review = await getPayrollRunReview(Number(id));
  const run = review.run;
  const items = review.items;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payslip Preview</span><h1>Run #{run.id} · {run.period_start} to {run.period_end}</h1><p className="muted">Formal payslip preview. Payroll is not marked paid from this page.</p></div></header>
        <section className="print-actions"><PrintButton label="Print payslips" /></section>
        <section className="grid cols-2">{items.map((item) => (<article className="card payslip-card" key={item.id}><div className="panel-title"><div><span className="eyebrow">Hidden Oasis</span><h2>Employee Payslip</h2><p className="muted">Payroll period: {run.period_start} to {run.period_end}</p><p className="muted">Payout date: {run.payout_date}</p></div><strong>{peso(item.net_pay)}</strong></div><div className="panel-title"><div><h3>{item.employee_name}</h3><p className="muted">Department: {item.department}</p></div><span className="muted">Run #{run.id}</span></div><div className="grid cols-2"><div><h3>Earnings</h3><p>Regular pay: {peso(item.regular_pay)}</p><p>Overtime pay: {peso(item.ot_pay)}</p><p>Night differential: {peso(item.night_diff_pay)}</p><p>Holiday pay: {peso(item.holiday_pay)}</p><p>Leave / freelance / other: {peso((item.paid_leave_pay || 0) + (item.freelance_pay || 0) + (item.other_earnings || 0))}</p><p><strong>Gross pay: {peso(item.gross_pay)}</strong></p></div><div><h3>Employee Deductions</h3><p>SSS employee share: {peso(item.sss_ee)}</p><p>PhilHealth employee share: {peso(item.philhealth_ee)}</p><p>Pag-IBIG employee share: {peso(item.pagibig_ee)}</p><p>Withholding tax: {peso(item.tax)}</p><p>Cash advance: {peso(item.cash_advance_deduction)}</p><p>Other deductions: {peso(item.other_deductions)}</p><p><strong>Total deductions: {peso(item.total_deductions)}</strong></p></div></div><div className="card soft"><h3>Employer Benefits / Contributions</h3><p className="muted">Shown separately for transparency. These are not deducted from net pay.</p><div className="grid cols-2"><div><p>SSS employer share: {peso(item.sss_er)}</p><p>SSS EC: {peso(item.sss_ec)}</p></div><div><p>PhilHealth employer share: {peso(item.philhealth_er)}</p><p>Pag-IBIG employer share: {peso(item.pagibig_er)}</p></div></div><p><strong>Total employer benefits: {peso(benefitsTotal(item))}</strong></p></div><div className="grid cols-3"><div><p className="muted">Mandatory deductions</p><strong>{peso(mandatoryDeductions(item))}</strong></div><div><p className="muted">Tax / advances / other</p><strong>{peso(taxAndOther(item))}</strong></div><div><p className="muted">Net pay</p><strong>{peso(item.net_pay)}</strong></div></div><hr /><div className="panel-title"><span>Received by: __________________________</span><span>Date: _______________</span></div></article>))}</section>
      </div>
    </Shell>
  );
}
