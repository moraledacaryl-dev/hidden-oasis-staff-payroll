import Link from "next/link";
import { redirect } from "next/navigation";
import { PayrollEmployeeLines } from "@/components/PayrollEmployeeLines";
import { Shell } from "@/components/Shell";
import { StatusBadge, severityTone } from "@/components/StatusBadge";
import { getPayrollPreview, peso } from "@/lib/api";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { currentCutoff, todayInManilaIso } from "@/lib/period";
import { currentSession } from "@/lib/session";

type PayrollPageProps = { searchParams?: Promise<{ start?: string; end?: string }> };
type Holiday = { id: number; holiday_date: string; name: string; holiday_type: string; active: boolean };

function validIsoDate(value?: string): value is string {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`)));
}

async function getActiveHolidays(start: string, end: string): Promise<Holiday[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/holidays`, {
    headers: await backendHeaders(false, true),
    cache: "no-store",
  });
  if (!response.ok) return [];
  const data = await response.json().catch(() => ({}));
  return (data.items || []).filter((holiday: Holiday) => holiday.active && holiday.holiday_date >= start && holiday.holiday_date <= end);
}

export default async function PayrollPage({ searchParams }: PayrollPageProps) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;

  const today = todayInManilaIso();
  const current = currentCutoff(today);
  const query = searchParams ? await searchParams : {};
  const requestedStart = validIsoDate(query.start) ? query.start : current.periodStart;
  const requestedEnd = validIsoDate(query.end) ? query.end : current.periodEnd;
  const periodStart = requestedStart <= requestedEnd ? requestedStart : requestedEnd;
  const periodEnd = requestedStart <= requestedEnd ? requestedEnd : requestedStart;
  const [preview, holidays] = await Promise.all([
    getPayrollPreview(periodStart, periodEnd),
    getActiveHolidays(periodStart, periodEnd),
  ]);
  const blockers = preview.checks.filter((check) => check.severity === "Blocker");
  const warnings = preview.checks.filter((check) => check.severity !== "Blocker");
  const leavePay = preview.items.reduce((sum, item) => sum + Number(item.paid_leave_pay || 0), 0);
  const holidayPay = preview.items.reduce((sum, item) => sum + Number(item.holiday_pay || 0), 0);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page payroll-page">
        <header className="payroll-hero">
          <div><span className="eyebrow">Payroll workflow</span><h1>Payroll preview</h1><p className="muted">Inspect employee earnings, holiday pay, deductions, cash advances, leave pay, and validation results for any date range before creating or approving a saved run.</p></div>
          <div className="payroll-actions"><Link className="button secondary" href="/cutoff">Open cutoff control</Link><Link className="button" href="/payroll/runs">Payroll runs</Link></div>
        </header>

        <section className="payroll-toolbar" data-payroll-preview-selector="true">
          <form method="get">
            <span className="payroll-toolbar-label">Preview dates</span>
            <label>Start date<input max={today} name="start" type="date" defaultValue={periodStart} /></label>
            <label>End date<input max={today} name="end" type="date" defaultValue={periodEnd} /></label>
            <button className="button" type="submit">Preview</button>
          </form>
          <p className="muted">Defaults to the current payroll cutoff, but you can preview any date range. Changing preview dates does not alter a saved payroll run.</p>
        </section>

        <section className="payroll-kpis">
          <div className="payroll-kpi"><span>Employees</span><strong>{preview.totals.employees}</strong><small>Included in calculation</small></div>
          <div className="payroll-kpi"><span>Gross pay</span><strong>{peso(preview.totals.gross_pay)}</strong><small>Before deductions</small></div>
          <div className="payroll-kpi"><span>Holiday pay</span><strong>{peso(holidayPay)}</strong><small>Holiday/rest-day premiums and eligible regular-holiday pay</small></div>
          <div className="payroll-kpi"><span>Leave pay</span><strong>{peso(leavePay)}</strong><small>Paid leave included separately</small></div>
          <div className="payroll-kpi"><span>Net payroll</span><strong>{peso(preview.totals.net_pay)}</strong><small>Expected payout total</small></div>
        </section>

        <section className="payroll-panel">
          <header><div><h2>Active holidays in this preview</h2><p>These date-specific classifications are considered by the payroll calculation. Special Non-Working Day premium is earned only from actual worked attendance.</p></div><StatusBadge label={`${holidays.length} holiday${holidays.length === 1 ? "" : "s"}`} /></header>
          <div className="payroll-panel-body">
            {holidays.length ? <div className="payroll-check-list">{holidays.map((holiday) => <div className="payroll-check" key={holiday.id}><StatusBadge label={holiday.holiday_type} tone={holiday.holiday_type === "Regular Holiday" ? "ok" : "warning"} /><div><strong>{holiday.holiday_date}</strong><p>{holiday.name}</p></div></div>)}</div> : <p className="muted">No active holidays are configured inside {periodStart} to {periodEnd}.</p>}
          </div>
        </section>

        <section className="payroll-overview">
          <section className="payroll-panel"><header><div><h2>Validation status</h2><p>Resolve blockers before draft creation. Warnings remain visible for review.</p></div><StatusBadge label={blockers.length ? `${blockers.length} blocker${blockers.length === 1 ? "" : "s"}` : warnings.length ? `${warnings.length} warning${warnings.length === 1 ? "" : "s"}` : "Clear"} tone={blockers.length ? "danger" : warnings.length ? "warning" : "ok"} /></header><div className="payroll-panel-body"><div className="payroll-check-list">{preview.checks.map((check, index) => <div className="payroll-check" key={`${check.category}-${index}`}><StatusBadge label={check.severity} tone={severityTone(check.severity)} /><div><strong>{check.category}</strong><p>{check.issue}</p><p>{check.recommended_action}</p></div></div>)}{preview.checks.length === 0 ? <p className="muted">No payroll validation issues.</p> : null}</div></div></section>
          <section className="payroll-panel"><header><div><h2>Workflow actions</h2><p>Keep calculation, approval, payment, and reporting as separate controlled stages.</p></div></header><div className="payroll-panel-body"><div className="payroll-next-list"><Link className="payroll-next" href="/cutoff"><div><strong>Create or review draft</strong><small>Open cutoff readiness and save the normal payroll run.</small></div><span>→</span></Link><Link className="payroll-next" href="/payroll/runs"><div><strong>Review saved runs</strong><small>Approve, revise, reopen, or inspect audit history.</small></div><span>→</span></Link><Link className="payroll-next" href="/payslips"><div><strong>Payslip distribution</strong><small>Open employee payslips for completed runs.</small></div><span>→</span></Link></div></div></section>
        </section>

        <section className="payroll-table-panel"><header><div><h2>Employee payroll lines</h2><p>Holiday Pay is shown separately from regular pay and leave pay. Open an employee to inspect earnings, deductions, cash advance deduction, and warnings.</p></div><StatusBadge label={`${preview.items.length} employees`} /></header><PayrollEmployeeLines items={preview.items} /></section>
      </div>
    </Shell>
  );
}
