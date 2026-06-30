import { redirect } from "next/navigation";
import { AttendanceDecisionButtons } from "@/components/AttendanceDecisionButtons";
import { PayrollDraftButton } from "@/components/PayrollDraftButton";
import { PayrollLifecycleButtons } from "@/components/PayrollLifecycleButtons";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getPayrollPreview, getPayrollRuns, numberText, peso } from "@/lib/api";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import {
  addIsoDays,
  isCompletedCutoff,
  latestCompletedCutoff,
  mondayOfWeek,
  payrollCutoffForMonth,
  todayInManilaIso,
} from "@/lib/period";
import { currentSession } from "@/lib/session";
import type { AttendanceException, PayrollRun } from "@/lib/api";
import type { ScheduleShift } from "@/lib/schedule-types";
import type { PayrollPreview } from "@/lib/types";

type CutoffPageProps = {
  searchParams?: Promise<{ month?: string; half?: string }>;
};

type WeekResponse = { ok: boolean; week_start: string; week_end: string; items: ScheduleShift[]; mode: string };

function metricTone(kind: "default" | "warning" | "danger" | "ok") {
  return `cutoff-metric ${kind}`;
}

function attendanceReason(item: AttendanceException, schedule?: ScheduleShift) {
  if (!schedule && item.actual_in) return "Rest day punch";
  if (Number(item.is_absent || 0) === 1) return "Scheduled absent";
  if (!item.actual_in || !item.actual_out) return "Missing log";
  if (item.ot_status === "Pending") return "OT review";
  if (item.attendance_status === "Needs Correction" || item.attendance_status === "Rejected") return "Correction";
  return "For review";
}

function scheduledText(schedule?: ScheduleShift) {
  if (!schedule) return "Rest day / no shift";
  const context = schedule.status || schedule.position || schedule.notes || "Scheduled";
  return `${schedule.start_time || "—"}–${schedule.end_time || "—"}${schedule.is_overnight ? " +1" : ""} · ${context}`;
}

function scheduleKey(employeeId: number, workDate: string) {
  return `${employeeId}:${workDate.slice(0, 10)}`;
}

function weekStartsForRange(periodStart: string, periodEnd: string) {
  const weeks: string[] = [];
  let current = mondayOfWeek(periodStart);
  while (current <= periodEnd) {
    weeks.push(current);
    current = addIsoDays(current, 7);
  }
  return weeks;
}

async function loadScheduleRange(periodStart: string, periodEnd: string): Promise<ScheduleShift[]> {
  const headers = await backendHeaders();
  const weeks = await Promise.all(
    weekStartsForRange(periodStart, periodEnd).map(async (weekStart) => {
      const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/week?week_start=${weekStart}`, { headers, cache: "no-store" });
      if (!response.ok) return [] as ScheduleShift[];
      const data = (await response.json()) as WeekResponse;
      return data.items || [];
    }),
  );
  return weeks.flat().filter((shift) => shift.shift_date >= periodStart && shift.shift_date <= periodEnd);
}

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
  let schedules: ScheduleShift[] = [];
  if (canSeePayroll && canReviewAttendance) {
    [preview, runs, exceptions, schedules] = await Promise.all([getPayrollPreview(periodStart, periodEnd), getPayrollRuns(), getAttendanceExceptions(periodStart, periodEnd), loadScheduleRange(periodStart, periodEnd)]);
  } else if (canSeePayroll) {
    [preview, runs] = await Promise.all([getPayrollPreview(periodStart, periodEnd), getPayrollRuns()]);
  } else if (canReviewAttendance) {
    [exceptions, schedules] = await Promise.all([getAttendanceExceptions(periodStart, periodEnd), loadScheduleRange(periodStart, periodEnd)]);
  }
  const scheduleMap = new Map(schedules.map((row) => [scheduleKey(Number(row.employee_id), row.shift_date), row]));
  const blockers = preview?.checks.filter((check) => check.severity === "Blocker") || [];
  const warnings = preview?.checks.filter((check) => check.severity !== "Blocker") || [];
  const reviewItems = blockers.length + exceptions.length;
  const ready = reviewItems === 0;
  const matchingRuns = runs.filter((run) => run.period_start === periodStart && run.period_end === periodEnd);
  const grossPay = preview?.totals.gross_pay || 0;
  const netPay = preview?.totals.net_pay || 0;
  const statusText = ready ? "Ready for owner review" : `${blockers.length} blocker${blockers.length === 1 ? "" : "s"} · ${exceptions.length} review item${exceptions.length === 1 ? "" : "s"}`;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page cutoff-page">
        <header className="page-header cutoff-hero">
          <div className="grid"><span className="eyebrow">Cutoff Control</span><h1>{periodStart} to {periodEnd}</h1><p className="muted">Normal attendance is pre-approved. Only blockers and review-required attendance stay in this queue.</p></div>
          <StatusBadge label={ready ? "ready" : "needs review"} tone={ready ? "ok" : "warning"} />
        </header>

        <section className="card cutoff-toolbar" data-cutoff-selector="true" data-payroll-cutoff-selector="true" data-period-start={periodStart} data-period-end={periodEnd} data-period-complete={periodComplete ? "true" : "false"} data-completed-default={periodComplete ? "true" : "false"}>
          <form className="cutoff-form" method="get"><span className="cutoff-toolbar-label">Cutoff</span><div className="field cutoff-field"><label htmlFor="cutoff-month">Month</label><input data-cutoff-month="true" data-payroll-cutoff-month="true" id="cutoff-month" max={today.slice(0, 7)} name="month" type="month" defaultValue={selected.month} /></div><div className="field cutoff-field compact"><label htmlFor="cutoff-half">Period</label><select data-cutoff-half="true" data-payroll-cutoff-half="true" id="cutoff-half" name="half" defaultValue={selected.half}><option value="first">1–15</option><option value="second">16–end</option></select></div><button className="primary-button" type="submit">View</button></form>
        </section>

        <section className={`cutoff-readiness ${ready ? "ok" : "warning"}`}><div><span className="eyebrow">Cutoff review</span><h2>{ready ? "Ready" : "Needs attention"}</h2><p>{ready ? "All normal attendance is pre-approved and no blockers remain." : "Accept items yourself or leave them For review."}</p></div><strong>{statusText}</strong></section>

        <section className="cutoff-metrics">
          {preview ? <div className={metricTone("default")}><span>Net payroll</span><strong>{peso(netPay)}</strong><small>Calculated</small></div> : <div className={metricTone("default")}><span>Payroll</span><strong>Restricted</strong><small>Operations view</small></div>}
          <div className={metricTone(blockers.length ? "danger" : "ok")}><span>Blockers</span><strong>{blockers.length}</strong><small>{blockers.length ? "Must clear" : "Clear"}</small></div><div className={metricTone(exceptions.length ? "warning" : "ok")}><span>Review queue</span><strong>{exceptions.length}</strong><small>{exceptions.length ? "For review" : "None"}</small></div><div className={metricTone(matchingRuns.length ? "ok" : "default")}><span>Saved runs</span><strong>{matchingRuns.length}</strong><small>This cutoff</small></div>
        </section>

        {canSeePayroll && preview ? <section className="cutoff-action-grid"><div className="card cutoff-draft-card" data-create-draft="true" data-create-payroll-draft="true"><div><span className="eyebrow">Next action</span><h2>Draft payroll run</h2><p className="muted">Create a saved payroll draft for review.</p></div><PayrollDraftButton periodStart={periodStart} periodEnd={periodEnd} payoutDate={payoutDate} /></div><div className="card cutoff-total-card"><span className="eyebrow">Payroll total</span><h2>{peso(grossPay)} gross</h2><p>{peso(netPay)} net after deductions</p></div></section> : null}

        <section className="card cutoff-review-card"><div className="panel-title"><div><span className="eyebrow">Review</span><h2>Review Queue</h2><p className="muted">Actual attendance is compared against the weekly schedule source. Normal matches are pre-approved.</p></div></div><div className="review-rule-strip"><span>Auto-approved: normal match</span><span>Review: major variance</span><span>Review: scheduled absent</span><span>Review: rest-day punch</span></div>{reviewItems ? <div className="table-wrap"><table><thead><tr><th>Issue</th><th>Employee</th><th>Scheduled</th><th>Actual</th><th>Action</th></tr></thead><tbody>{blockers.map((check, index) => (<tr key={`blocker-${check.category}-${index}`}><td><StatusBadge label="Blocker" tone="danger" /></td><td><strong>{check.category}</strong><p className="muted">{check.issue}</p></td><td colSpan={2}>{check.recommended_action}</td><td>—</td></tr>))}{canReviewAttendance ? exceptions.slice(0, 25).map((item) => { const schedule = scheduleMap.get(scheduleKey(Number(item.employee_id), item.work_date)); return <tr key={`attendance-${item.id}`}><td><StatusBadge label={attendanceReason(item, schedule)} tone="warning" /></td><td><strong>{item.full_name}</strong><p className="muted">{item.work_date}</p></td><td>{scheduledText(schedule)}</td><td>{item.actual_in || "—"}–{item.actual_out || "—"}<p className="muted">OT {numberText(item.detected_ot_hours)}</p></td><td><AttendanceDecisionButtons timeLogId={item.id} detectedOtHours={Number(item.detected_ot_hours || 0)} /></td></tr>; }) : null}</tbody></table></div> : <div className="empty-state"><strong>No review items</strong><p>Attendance is pre-approved and there are no payroll blockers for this cutoff.</p></div>}{exceptions.length > 25 ? <p className="muted">Showing first 25 review items.</p> : null}{warnings.length ? <details className="coverage-review soft"><summary><div><h2>Warnings not blocking draft</h2><p className="muted">{warnings.length} warning{warnings.length === 1 ? "" : "s"} for awareness.</p></div></summary><div className="coverage-review-body action-list">{warnings.map((check, index) => (<div className="action-item" key={`warning-${check.category}-${index}`}><StatusBadge label={check.severity} tone="warning" /><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>))}</div></details> : null}</section>

        {canSeePayroll ? <section className="card"><div className="panel-title"><div><h2>Saved payroll runs</h2><p className="muted">Draft, review, approve, reopen.</p></div></div>{matchingRuns.length ? <div className="table-wrap"><table><thead><tr><th>ID</th><th>Label</th><th>Status</th><th>Prepared by</th><th>Employees</th><th>Net</th><th>Created</th><th>Action</th></tr></thead><tbody>{matchingRuns.map((run) => (<tr key={run.id}><td>{run.id}</td><td>{run.run_label}</td><td>{run.status}</td><td>{run.prepared_by || "—"}</td><td>{run.totals?.employees ?? 0}</td><td>{peso(run.totals?.net_pay || 0)}</td><td>{run.created_at}</td><td><PayrollLifecycleButtons runId={run.id} status={run.status} role={session.role_key} /></td></tr>))}</tbody></table></div> : <div className="empty-state"><strong>No payroll draft yet</strong><p>Create a draft after reviewing blockers and review queue items.</p></div>}</section> : null}
      </div>
    </Shell>
  );
}
