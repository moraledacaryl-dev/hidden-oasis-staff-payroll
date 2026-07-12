import Link from "next/link";
import { redirect } from "next/navigation";
import { PayrollEmployeeLines } from "@/components/PayrollEmployeeLines";
import { Shell } from "@/components/Shell";
import { StatusBadge, severityTone } from "@/components/StatusBadge";
import { getPayrollPreview, peso } from "@/lib/api";
import { currentCutoff, payrollCutoffForMonth, todayInManilaIso } from "@/lib/period";
import { currentSession } from "@/lib/session";

type PayrollPageProps = { searchParams?: Promise<{ month?: string; half?: string }> };

export default async function PayrollPage({ searchParams }: PayrollPageProps) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;

  const today = todayInManilaIso();
  const current = currentCutoff(today);
  const query = searchParams ? await searchParams : {};
  const defaultMonth = current.periodStart.slice(0, 7);
  const defaultHalf = current.periodStart.slice(8, 10) === "01" ? "first" : "second";
  const half = query.half === "first" || query.half === "second" ? query.half : defaultHalf;
  const selected = payrollCutoffForMonth(query.month || defaultMonth, half) || { month: defaultMonth, half: defaultHalf, periodStart: current.periodStart, periodEnd: current.periodEnd, payoutDate: current.payoutDate };
  const preview = await getPayrollPreview(selected.periodStart, selected.periodEnd);
  const blockers = preview.checks.filter((check) => check.severity === "Blocker");
  const warnings = preview.checks.filter((check) => check.severity !== "Blocker");
  const leavePay = preview.items.reduce((sum, item) => sum + Number(item.paid_leave_pay || 0), 0);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page payroll-page">
        <header className="payroll-hero">
          <div><span className="eyebrow">Payroll workflow</span><h1>Payroll preview</h1><p className="muted">Inspect employee earnings, deductions, cash advances, leave pay, and validation results before creating or approving a saved run.</p></div>
          <div className="payroll-actions"><Link className="button secondary" href={`/cutoff?month=${selected.month}&half=${selected.half}`}>Open cutoff control</Link><Link className="button" href="/payroll/runs">Payroll runs</Link></div>
        </header>

        <section className="payroll-toolbar" data-payroll-preview-selector="true"><form method="get"><span className="payroll-toolbar-label">Preview period</span><label>Month<input max={today.slice(0, 7)} name="month" type="month" defaultValue={selected.month} /></label><label>Period<select name="half" defaultValue={selected.half}><option value="first">1–15</option><option value="second">16–end</option></select></label><button className="button" type="submit">Preview</button></form></section>

        <section className="payroll-kpis">
          <div className="payroll-kpi"><span>Employees</span><strong>{preview.totals.employees}</strong><small>Included in calculation</small></div>
          <div className="payroll-kpi"><span>Gross pay</span><strong>{peso(preview.totals.gross_pay)}</strong><small>Before deductions</small></div>
          <div className="payroll-kpi"><span>Leave pay</span><strong>{peso(leavePay)}</strong><small>Paid leave included</small></div>
          <div className="payroll-kpi"><span>Net payroll</span><strong>{peso(preview.totals.net_pay)}</strong><small>Expected payout total</small></div>
        </section>

        <section className="payroll-overview">
          <section className="payroll-panel"><header><div><h2>Validation status</h2><p>Resolve blockers before draft creation. Warnings remain visible for review.</p></div><StatusBadge label={blockers.length ? `${blockers.length} blocker${blockers.length === 1 ? "" : "s"}` : warnings.length ? `${warnings.length} warning${warnings.length === 1 ? "" : "s"}` : "Clear"} tone={blockers.length ? "danger" : warnings.length ? "warning" : "ok"} /></header><div className="payroll-panel-body"><div className="payroll-check-list">{preview.checks.map((check, index) => <div className="payroll-check" key={`${check.category}-${index}`}><StatusBadge label={check.severity} tone={severityTone(check.severity)} /><div><strong>{check.category}</strong><p>{check.issue}</p><p>{check.recommended_action}</p></div></div>)}{preview.checks.length === 0 ? <p className="muted">No payroll validation issues.</p> : null}</div></div></section>
          <section className="payroll-panel"><header><div><h2>Workflow actions</h2><p>Keep calculation, approval, payment, and reporting as separate controlled stages.</p></div></header><div className="payroll-panel-body"><div className="payroll-next-list"><Link className="payroll-next" href={`/cutoff?month=${selected.month}&half=${selected.half}`}><div><strong>Create or review draft</strong><small>Open cutoff readiness and save the run.</small></div><span>→</span></Link><Link className="payroll-next" href="/payroll/runs"><div><strong>Review saved runs</strong><small>Approve, revise, reopen, or inspect audit history.</small></div><span>→</span></Link><Link className="payroll-next" href="/payslips"><div><strong>Payslip distribution</strong><small>Open employee payslips for completed runs.</small></div><span>→</span></Link></div></div></section>
        </section>

        <section className="payroll-table-panel"><header><div><h2>Employee payroll lines</h2><p>Open an employee to inspect source earnings, deductions, cash advance deduction, and warnings.</p></div><StatusBadge label={`${preview.items.length} employees`} /></header><PayrollEmployeeLines items={preview.items} /></section>
      </div>
    </Shell>
  );
}
