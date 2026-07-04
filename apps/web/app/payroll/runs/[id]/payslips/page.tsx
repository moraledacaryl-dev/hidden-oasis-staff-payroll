import Link from "next/link";
import { redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { getPayrollRunReview, numberText, peso } from "@/lib/api";
import type { PayrollReviewItem, PayrollRun } from "@/lib/api";
import { currentSession } from "@/lib/session";
import "./print.css";

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

function PayslipCopy({ item, run, copyLabel, companyCopy = false }: { item: PayrollReviewItem; run: PayrollRun; copyLabel: string; companyCopy?: boolean }) {
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

export default async function PayslipPreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId) || runId <= 0) {
    return (
      <Shell allowedRoles={["owner", "payroll"]}>
        <div className="page"><section className="card"><h1>Invalid payroll run</h1><p className="muted">Open payslips from Payroll Runs instead.</p><Link className="primary-link" href="/payroll/runs">Back to payroll runs</Link></section></div>
      </Shell>
    );
  }

  let review;
  try {
    review = await getPayrollRunReview(runId);
  } catch {
    return (
      <Shell allowedRoles={["owner", "payroll"]}>
        <div className="page">
          <header className="page-header"><div className="grid"><span className="eyebrow">Payslips</span><h1>Run #{runId} unavailable</h1></div></header>
          <section className="card">
            <div className="action-row"><Link className="primary-link" href="/payroll/runs">Back to payroll runs</Link><Link className="primary-link" href="/payroll">Current payroll</Link></div>
          </section>
        </div>
      </Shell>
    );
  }

  const run = review.run;
  const items = review.items || [];

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page payslip-page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payslip Preview</span>
            <h1>Run #{run.id}</h1>
            <p className="muted">{run.period_start} to {run.period_end}. Employer contributions stay in payroll reports, not on employee payslips.</p>
             {run.superseded_by_run_id ? <p className="muted">This is an older payroll version superseded by Run #{run.superseded_by_run_id}. Use it for audit/history only; normal Payslip Distribution should use the latest active version.</p> : null}
             {run.revision_of_run_id ? <p className="muted">This is a revision of Run #{run.revision_of_run_id}. For already-paid payroll, distribute/pay only the adjustment difference unless this run is explicitly approved as the active corrected version.</p> : null}
            <div className="action-row"><Link className="primary-link" href="/payroll/runs">All runs</Link><Link className="primary-link" href={`/payroll/runs/${run.id}/reports`}>Report</Link><Link className="primary-link" href={`/payroll/runs/${run.id}/audit`}>Audit</Link></div>
          </div>
        </header>
        <section className="print-actions"><PrintButton label="Print payslips" /></section>
        {items.length === 0 ? <section className="card"><h2>No payroll items</h2><p className="muted">This run has no saved employee payroll lines yet.</p></section> : null}
        <section className="payslip-grid">
          {items.map((item) => (
            <article className="payslip-sheet" key={item.id}>
              <PayslipCopy item={item} run={run} copyLabel="Employee Copy" />
              <PayslipCopy item={item} run={run} copyLabel="Company Copy" companyCopy />
            </article>
          ))}
        </section>
      </div>
    </Shell>
  );
}
