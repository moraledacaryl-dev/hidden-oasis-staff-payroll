import { redirect } from "next/navigation";
import { AttendanceDecisionButtons } from "@/components/AttendanceDecisionButtons";
import { MetricCard } from "@/components/MetricCard";
import { PayrollDraftButton } from "@/components/PayrollDraftButton";
import { PayrollLifecycleButtons } from "@/components/PayrollLifecycleButtons";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getPayrollPreview, getPayrollRuns, numberText, peso } from "@/lib/api";
import {
  isCompletedCutoff,
  latestCompletedCutoff,
  payrollCutoffForMonth,
  todayInManilaIso,
} from "@/lib/period";
import { currentSession } from "@/lib/session";
import type { AttendanceException, PayrollRun } from "@/lib/api";
import type { PayrollPreview } from "@/lib/types";

type CutoffPageProps = {
  searchParams?: Promise<{ month?: string; half?: string }>;
};

export default async function CutoffPage({ searchParams }: CutoffPageProps) {
  const session = await currentSession();
  if (!session) redirect("/login");
  const today = todayInManilaIso();
  const latest = latestCompletedCutoff(today);
  const query = searchParams ? await searchParams : {};
  const half = query.half === "first" || query.half === "second" ? query.half : latest.half;
  const selected = payrollCutoffForMonth(query.month || latest.month, half) || latest;
  const { periodStart, periodEnd, payoutDate } = selected;
  const periodComplete = isCompletedCutoff(selected, today);
  const canSeePayroll = session.role_key === "owner" || session.role_key === "payroll";
  const canReviewAttendance = session.role_key === "owner" || session.role_key === "supervisor";
  let preview: PayrollPreview | null = null;
  let exceptions: AttendanceException[] = [];
  let runs: PayrollRun[] = [];
  if (canSeePayroll) {
    [preview, runs] = await Promise.all([getPayrollPreview(periodStart, periodEnd), getPayrollRuns()]);
  }
  if (canReviewAttendance) {
    exceptions = await getAttendanceExceptions(periodStart, periodEnd);
  }
  const blockers = preview?.checks.filter((check) => check.severity === "Blocker") || [];
  const ready = blockers.length === 0 && exceptions.length === 0;
  const matchingRuns = runs.filter((run) => run.period_start === periodStart && run.period_end === periodEnd);

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Cutoff Control</span><h1>{periodStart} to {periodEnd}</h1><p className="muted">{canSeePayroll ? "Check blockers, save draft, route approval." : "Attendance review only."}</p></div><StatusBadge label={ready ? "ready" : "not ready"} tone={ready ? "ok" : "warning"} /></header>
        <section
          className="card cutoff-selector-card"
          data-cutoff-selector="true"
          data-payroll-cutoff-selector="true"
          data-period-start={periodStart}
          data-period-end={periodEnd}
          data-period-complete={periodComplete ? "true" : "false"}
          data-completed-default={periodComplete ? "true" : "false"}
        >
          <form className="cutoff-form" method="get">
            <div className="field cutoff-field">
              <label htmlFor="cutoff-month">Month</label>
              <input data-cutoff-month="true" data-payroll-cutoff-month="true" id="cutoff-month" max={today.slice(0, 7)} name="month" type="month" defaultValue={selected.month} />
            </div>
            <div className="field cutoff-field">
              <label htmlFor="cutoff-half">Cutoff</label>
              <select data-cutoff-half="true" data-payroll-cutoff-half="true" id="cutoff-half" name="half" defaultValue={selected.half}>
                <option value="first">1–15</option>
                <option value="second">16–end</option>
              </select>
            </div>
            <button className="primary-button" type="submit">View cutoff</button>
          </form>
        </section>
        <section className="grid cols-4">{preview ? <MetricCard label="Net payroll" value={peso(preview.totals.net_pay)} detail="Calculated" /> : <MetricCard label="Payroll" value="Restricted" detail="Operations view" />}<MetricCard label="Blockers" value={String(blockers.length)} detail="Must clear" /><MetricCard label="Exceptions" value={String(exceptions.length)} detail="Open" /><MetricCard label="Saved runs" value={String(matchingRuns.length)} detail="This cutoff" /></section>
        {canSeePayroll && preview ? <section className="grid cols-3"><div className="card" data-create-draft="true" data-create-payroll-draft="true"><strong>Draft payroll run</strong><p className="muted">Creates a saved draft. Approval stays separate.</p><PayrollDraftButton periodStart={periodStart} periodEnd={periodEnd} payoutDate={payoutDate} /></div><div className="card"><strong>Gross / net</strong><p>{peso(preview.totals.gross_pay)} gross</p><p>{peso(preview.totals.net_pay)} net</p></div><div className="card"><strong>Readiness</strong><p className="muted">{ready ? "Ready for owner review." : "Clear blockers first."}</p></div></section> : null}
        {canSeePayroll ? <section className="card"><div className="panel-title"><div><h2>Saved payroll runs</h2><p className="muted">Draft, review, approve, reopen.</p></div></div><div className="table-wrap"><table><thead><tr><th>ID</th><th>Label</th><th>Status</th><th>Prepared by</th><th>Employees</th><th>Net</th><th>Created</th><th>Action</th></tr></thead><tbody>{matchingRuns.map((run) => (<tr key={run.id}><td>{run.id}</td><td>{run.run_label}</td><td>{run.status}</td><td>{run.prepared_by || "—"}</td><td>{run.totals?.employees ?? 0}</td><td>{peso(run.totals?.net_pay || 0)}</td><td>{run.created_at}</td><td><PayrollLifecycleButtons runId={run.id} status={run.status} role={session.role_key} /></td></tr>))}{matchingRuns.length === 0 ? <tr><td colSpan={8}>No saved payroll draft for this cutoff yet.</td></tr> : null}</tbody></table></div></section> : null}
        {canReviewAttendance ? <section className="card"><div className="panel-title"><div><h2>Attendance actions</h2><p className="muted">Top exceptions.</p></div></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Status</th><th>OT</th><th>Action</th></tr></thead><tbody>{exceptions.slice(0, 10).map((item) => (<tr key={item.id}><td>{item.work_date}</td><td>{item.full_name}</td><td>{item.is_absent ? "Absent" : item.attendance_status}</td><td>{numberText(item.detected_ot_hours)}</td><td><AttendanceDecisionButtons timeLogId={item.id} detectedOtHours={Number(item.detected_ot_hours || 0)} /></td></tr>))}{exceptions.length === 0 ? <tr><td colSpan={5}>No attendance exceptions.</td></tr> : null}</tbody></table></div></section> : null}
        {preview ? <section className="card"><div className="panel-title"><div><h2>Payroll QA</h2><p className="muted">Current blockers and warnings.</p></div></div><div className="action-list">{preview.checks.map((check, index) => (<div className="action-item" key={`${check.category}-${index}`}><StatusBadge label={check.severity} tone={check.severity === "Blocker" ? "danger" : "warning"} /><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>))}</div></section> : null}
      </div>
    </Shell>
  );
}
