import { numberText, peso } from "@/lib/api";
import type { PayrollReviewItem, PayrollRun } from "@/lib/api";
export type PayslipItem = Pick<PayrollReviewItem, "employee_name" | "department" | "regular_hours" | "approved_ot_hours" | "night_diff_hours" | "net_pay" | "regular_pay" | "ot_pay" | "night_diff_pay" | "holiday_pay" | "paid_leave_pay" | "freelance_pay" | "other_earnings" | "gross_pay" | "sss_ee" | "philhealth_ee" | "pagibig_ee" | "tax" | "cash_advance_deduction" | "other_deductions" | "total_deductions" | "leave_summary">;
export type PayslipRun = Pick<PayrollRun, "id" | "period_start" | "period_end" | "payout_date">;

function mandatoryDeductions(item: { sss_ee: number; philhealth_ee: number; pagibig_ee: number }) {
  return Number(item.sss_ee || 0) + Number(item.philhealth_ee || 0) + Number(item.pagibig_ee || 0);
}
function taxAdvanceOther(item: { tax: number; cash_advance_deduction: number; other_deductions: number }) {
  return Number(item.tax || 0) + Number(item.cash_advance_deduction || 0) + Number(item.other_deductions || 0);
}

function lineAmount(...values: Array<number | null | undefined>): number {
  return values.reduce<number>((sum, value) => sum + Number(value || 0), 0);
}

function hasValue(value: number | null | undefined) {
  return Number(value || 0) > 0;
}

export function PayslipCopy({ item, run, copyLabel, companyCopy = false }: { item: PayslipItem; run: PayslipRun; copyLabel: string; companyCopy?: boolean }) {
  return (
    <div className={`payslip-copy${companyCopy ? " company-copy" : ""}`}>
      <div className="copy-label">{copyLabel}</div>
      <div className="payslip-top">
        <div><span className="eyebrow">Hidden Oasis</span><h2>Employee Payslip</h2><div className="payslip-meta"><p className="muted">Period: {run.period_start} to {run.period_end}</p><p className="muted">Payout: {run.payout_date} · Run #{run.id}</p></div></div>
        <div className="payslip-net"><span>Net Pay</span><strong>{peso(item.net_pay)}</strong></div>
      </div>
      <div className="payslip-employee"><div><h3>{item.employee_name}</h3><p className="muted">Department: {item.department}</p></div></div>
      <div className="payslip-summary">
        <div><span>Regular hours</span><strong>{numberText(item.regular_hours)} hrs</strong></div>
        <div><span>Overtime hours</span><strong>{hasValue(item.approved_ot_hours) ? `${numberText(item.approved_ot_hours)} hrs` : "—"}</strong></div>
        <div><span>Night diff hours</span><strong>{hasValue(item.night_diff_hours) ? `${numberText(item.night_diff_hours)} hrs` : "—"}</strong></div>
      </div>
      <div className="payslip-columns">
        <section>
          <h3>Earnings</h3>
          <p><span>Regular pay</span><strong>{peso(item.regular_pay)}</strong></p>
          {hasValue(item.ot_pay) ? <p><span>Overtime pay</span><strong>{peso(item.ot_pay)}</strong></p> : null}
          {hasValue(item.night_diff_pay) ? <p><span>Night differential</span><strong>{peso(item.night_diff_pay)}</strong></p> : null}
          {hasValue(item.holiday_pay) ? <p><span>Holiday pay</span><strong>{peso(item.holiday_pay)}</strong></p> : null}
          {hasValue(lineAmount(item.paid_leave_pay, item.freelance_pay, item.other_earnings)) ? <p><span>Leave / other earnings</span><strong>{peso(lineAmount(item.paid_leave_pay, item.freelance_pay, item.other_earnings))}</strong></p> : null}
          {item.leave_summary?.length ? <div className="leave-lines"><strong>Paid leave details</strong>{item.leave_summary.map((line) => (<span key={line}>{line}</span>))}</div> : null}
          <p className="total-line"><span>Gross pay</span><strong>{peso(item.gross_pay)}</strong></p>
        </section>
        <section>
          <h3>Deductions</h3>
          <p><span>SSS</span><strong>{peso(item.sss_ee)}</strong></p>
          <p><span>PhilHealth</span><strong>{peso(item.philhealth_ee)}</strong></p>
          <p><span>Pag-IBIG</span><strong>{peso(item.pagibig_ee)}</strong></p>
          <p><span>Withholding tax</span><strong>{peso(item.tax)}</strong></p>
          <p><span>Cash advance</span><strong>{peso(item.cash_advance_deduction)}</strong></p>
          <p><span>Other deductions</span><strong>{peso(item.other_deductions)}</strong></p>
          <p className="total-line"><span>Total deductions</span><strong>{peso(item.total_deductions)}</strong></p>
        </section>
      </div>
      <div className="payslip-summary"><div><span>Mandatory deductions</span><strong>{peso(mandatoryDeductions(item))}</strong></div><div><span>Tax / advances / other</span><strong>{peso(taxAdvanceOther(item))}</strong></div><div><span>Net pay</span><strong>{peso(item.net_pay)}</strong></div></div>
      <div className="payslip-signature"><span>Received by: __________________________</span><span>Date: _______________</span></div>
    </div>
  );
}
