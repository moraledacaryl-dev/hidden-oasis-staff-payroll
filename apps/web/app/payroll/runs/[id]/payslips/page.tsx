import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { getPayrollRunReview, peso } from "@/lib/api";

function mandatoryDeductions(item: { sss_ee: number; philhealth_ee: number; pagibig_ee: number }) {
  return Number(item.sss_ee || 0) + Number(item.philhealth_ee || 0) + Number(item.pagibig_ee || 0);
}

function taxAdvanceOther(item: { tax: number; cash_advance_deduction: number; other_deductions: number }) {
  return Number(item.tax || 0) + Number(item.cash_advance_deduction || 0) + Number(item.other_deductions || 0);
}

export default async function PayslipPreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const review = await getPayrollRunReview(Number(id));
  const run = review.run;
  const items = review.items;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page payslip-page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payslip Preview</span><h1>Run #{run.id} · {run.period_start} to {run.period_end}</h1><p className="muted">Employee payslip copy. Employer contributions are kept in payroll reports, not shown here.</p></div></header>
        <section className="print-actions"><PrintButton label="Print payslips" /></section>
        <section className="payslip-grid">{items.map((item) => (<article className="card payslip-card" key={item.id}><div className="payslip-top"><div><span className="eyebrow">Hidden Oasis</span><h2>Employee Payslip</h2><div className="payslip-meta"><p className="muted">Period: {run.period_start} to {run.period_end}</p><p className="muted">Payout: {run.payout_date} · Run #{run.id}</p></div></div><div className="payslip-net"><span>Net Pay</span><strong>{peso(item.net_pay)}</strong></div></div><div className="payslip-employee"><div><h3>{item.employee_name}</h3><p className="muted">Department: {item.department}</p></div></div><div className="payslip-columns"><section><h3>Earnings</h3><p><span>Regular pay</span><strong>{peso(item.regular_pay)}</strong></p><p><span>Overtime pay</span><strong>{peso(item.ot_pay)}</strong></p><p><span>Night differential</span><strong>{peso(item.night_diff_pay)}</strong></p><p><span>Holiday pay</span><strong>{peso(item.holiday_pay)}</strong></p><p><span>Leave / other earnings</span><strong>{peso((item.paid_leave_pay || 0) + (item.freelance_pay || 0) + (item.other_earnings || 0))}</strong></p>{item.leave_summary?.length ? <div className="leave-lines"><strong>Paid leave details</strong>{item.leave_summary.map((line) => (<span key={line}>{line}</span>))}</div> : null}<p className="total-line"><span>Gross pay</span><strong>{peso(item.gross_pay)}</strong></p></section><section><h3>Deductions</h3><p><span>SSS</span><strong>{peso(item.sss_ee)}</strong></p><p><span>PhilHealth</span><strong>{peso(item.philhealth_ee)}</strong></p><p><span>Pag-IBIG</span><strong>{peso(item.pagibig_ee)}</strong></p><p><span>Withholding tax</span><strong>{peso(item.tax)}</strong></p><p><span>Cash advance</span><strong>{peso(item.cash_advance_deduction)}</strong></p><p><span>Other deductions</span><strong>{peso(item.other_deductions)}</strong></p><p className="total-line"><span>Total deductions</span><strong>{peso(item.total_deductions)}</strong></p></section></div><div className="payslip-summary"><div><span>Mandatory deductions</span><strong>{peso(mandatoryDeductions(item))}</strong></div><div><span>Tax / advances / other</span><strong>{peso(taxAdvanceOther(item))}</strong></div><div><span>Net pay</span><strong>{peso(item.net_pay)}</strong></div></div><div className="payslip-signature"><span>Received by: __________________________</span><span>Date: _______________</span></div></article>))}</section>
      </div>
    </Shell>
  );
}
