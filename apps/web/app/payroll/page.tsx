import Link from "next/link";
import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge, severityTone } from "@/components/StatusBadge";
import { getPayrollPreview, numberText, peso } from "@/lib/api";
import { currentCutoff, payrollCutoffForMonth, todayInManilaIso } from "@/lib/period";
import { currentSession } from "@/lib/session";

type PayrollPageProps = {
  searchParams?: Promise<{ month?: string; half?: string }>;
};

export default async function PayrollPage({ searchParams }: PayrollPageProps) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }

  const today = todayInManilaIso();
  const current = currentCutoff(today);
  const query = searchParams ? await searchParams : {};
  const defaultMonth = current.periodStart.slice(0, 7);
  const defaultHalf = current.periodStart.slice(8, 10) === "01" ? "first" : "second";
  const half = query.half === "first" || query.half === "second" ? query.half : defaultHalf;
  const selected = payrollCutoffForMonth(query.month || defaultMonth, half) || {
    month: defaultMonth,
    half: defaultHalf,
    periodStart: current.periodStart,
    periodEnd: current.periodEnd,
    payoutDate: current.payoutDate,
  };
  const { periodStart, periodEnd } = selected;
  const preview = await getPayrollPreview(periodStart, periodEnd);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payroll</span>
            <h1>Cutoff preview</h1>
            <p className="muted">Check totals before saving a run. You can preview any cutoff even before a draft exists.</p>
          </div>
          <div className="badge-row"><StatusBadge label={`${periodStart} to ${periodEnd}`} tone="warning" /><StatusBadge label={preview.mode} tone="warning" /></div>
        </header>

        <section className="card cutoff-toolbar" data-payroll-preview-selector="true">
          <form className="cutoff-form" method="get">
            <span className="cutoff-toolbar-label">Preview period</span>
            <div className="field cutoff-field">
              <label htmlFor="payroll-preview-month">Month</label>
              <input id="payroll-preview-month" max={today.slice(0, 7)} name="month" type="month" defaultValue={selected.month} />
            </div>
            <div className="field cutoff-field compact">
              <label htmlFor="payroll-preview-half">Period</label>
              <select id="payroll-preview-half" name="half" defaultValue={selected.half}>
                <option value="first">1–15</option>
                <option value="second">16–end</option>
              </select>
            </div>
            <button className="primary-button" type="submit">Preview</button>
          </form>
        </section>

        <section className="grid cols-4"><MetricCard label="Employees" value={preview.totals.employees} /><MetricCard label="Gross pay" value={peso(preview.totals.gross_pay)} /><MetricCard label="Leave pay" value={peso(preview.items.reduce((sum, item) => sum + Number(item.paid_leave_pay || 0), 0))} /><MetricCard label="Net pay" value={peso(preview.totals.net_pay)} /></section>
        <section className="grid cols-2">
          <div className="card"><div className="panel-title"><div><h2>QA checks</h2><p className="muted">Blockers and warnings.</p></div><StatusBadge label={preview.summary} tone={preview.checks.some((c) => c.severity === "Blocker") ? "danger" : "warning"} /></div><div className="action-list">{preview.checks.map((check, index) => (<div className="action-item" key={`${check.category}-${index}`}><div className="badge-row"><StatusBadge label={check.severity} tone={severityTone(check.severity)} /></div><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>))}{preview.checks.length === 0 ? <p className="muted">No QA checks.</p> : null}</div></div>
          <div className="card"><div className="panel-title"><div><h2>Next steps</h2><p className="muted">Keep each action separate.</p></div></div><div className="action-list"><Link className="action-item" href={`/cutoff?month=${selected.month}&half=${selected.half}`}><strong>Save draft</strong><p className="muted">Open Cutoff Control for this period.</p></Link><Link className="action-item" href="/payroll/runs"><strong>Review runs</strong><p className="muted">Approve or reopen saved runs.</p></Link><Link className="action-item" href="/payroll/runs"><strong>Mark paid</strong><p className="muted">Owner only, after approval.</p></Link></div></div>
        </section>
        <section className="card"><div className="panel-title"><div><h2>Employee lines</h2><p className="muted">Computed preview for the selected cutoff.</p></div></div><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Regular hrs</th><th>OT hrs</th><th>Leave days</th><th>Leave pay</th><th>Gross</th><th>Deductions</th><th>CA deduction</th><th>Net</th><th>Warnings</th></tr></thead><tbody>{preview.items.map((item) => (<tr key={item.employee_id}><td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code}</span></td><td>{numberText(item.regular_hours)}</td><td>{numberText(item.approved_ot_hours)}</td><td>{numberText(item.paid_leave_days)}</td><td>{item.paid_leave_pay ? peso(item.paid_leave_pay) : "—"}</td><td>{peso(item.gross_pay)}</td><td>{peso(item.total_deductions)}</td><td>{peso(item.cash_advance_deduction)}</td><td><strong>{peso(item.net_pay)}</strong></td><td>{item.warnings?.length ? `${item.warnings.length} warning(s)` : "—"}</td></tr>))}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
