import { AttendanceDecisionButtons } from "@/components/AttendanceDecisionButtons";
import { MetricCard } from "@/components/MetricCard";
import { PayrollDraftButton } from "@/components/PayrollDraftButton";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews, getPayrollPreview, getPayrollRuns, numberText, peso } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";
const PAYOUT_DATE = "2026-06-15";

export default async function CutoffPage() {
  const [preview, exceptions, reviews, runs] = await Promise.all([
    getPayrollPreview(DEFAULT_START, DEFAULT_END),
    getAttendanceExceptions(DEFAULT_START, DEFAULT_END),
    getAttendanceReviews(DEFAULT_START, DEFAULT_END),
    getPayrollRuns(),
  ]);
  const blockers = preview.checks.filter((check) => check.severity === "Blocker");
  const ready = blockers.length === 0 && exceptions.length === 0;
  const matchingRuns = runs.filter((run) => run.period_start === DEFAULT_START && run.period_end === DEFAULT_END);

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Cutoff Control</span><h1>{DEFAULT_START} to {DEFAULT_END}</h1><p className="muted">One readiness cockpit before payroll approval. Draft save is enabled; release remains disabled.</p></div><StatusBadge label={ready ? "ready" : "not ready"} tone={ready ? "success" : "warning"} /></header>
        <section className="grid cols-4"><MetricCard label="Net payroll" value={peso(preview.totals.net_pay)} detail="Preview only" /><MetricCard label="Blockers" value={String(blockers.length)} detail="Must be zero" /><MetricCard label="Exceptions" value={String(exceptions.length)} detail="Attendance queue" /><MetricCard label="Saved runs" value={String(matchingRuns.length)} detail="Draft / review only" /></section>
        <section className="grid cols-3"><div className="card"><strong>Draft payroll run</strong><p className="muted">Creates payroll_runs + payroll_items only. It does not approve or pay payroll.</p><PayrollDraftButton periodStart={DEFAULT_START} periodEnd={DEFAULT_END} payoutDate={PAYOUT_DATE} /></div><div className="card"><strong>Gross / net</strong><p>{peso(preview.totals.gross_pay)} gross</p><p>{peso(preview.totals.net_pay)} net</p></div><div className="card"><strong>Readiness</strong><p className="muted">{ready ? "Ready for saved draft / owner review." : "Clear blockers and attendance exceptions first."}</p></div></section>
        <section className="card"><div className="panel-title"><div><h2>Saved payroll runs</h2><p className="muted">Existing runs for this cutoff. Release/pay is still disabled.</p></div></div><div className="table-wrap"><table><thead><tr><th>ID</th><th>Label</th><th>Status</th><th>Prepared by</th><th>Employees</th><th>Net</th><th>Created</th></tr></thead><tbody>{matchingRuns.map((run) => (<tr key={run.id}><td>{run.id}</td><td>{run.run_label}</td><td>{run.status}</td><td>{run.prepared_by || "—"}</td><td>{run.totals?.employees ?? 0}</td><td>{peso(run.totals?.net_pay || 0)}</td><td>{run.created_at}</td></tr>))}{matchingRuns.length === 0 ? <tr><td colSpan={7}>No saved payroll draft for this cutoff yet.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><div className="panel-title"><div><h2>Immediate attendance actions</h2><p className="muted">Top exceptions from the supervisor queue.</p></div></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Status</th><th>OT</th><th>Action</th></tr></thead><tbody>{exceptions.slice(0, 10).map((item) => (<tr key={item.id}><td>{item.work_date}</td><td>{item.full_name}</td><td>{item.is_absent ? "Absent" : item.attendance_status}</td><td>{numberText(item.detected_ot_hours)}</td><td><AttendanceDecisionButtons timeLogId={item.id} detectedOtHours={Number(item.detected_ot_hours || 0)} /></td></tr>))}{exceptions.length === 0 ? <tr><td colSpan={5}>No attendance exceptions.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><div className="panel-title"><div><h2>Payroll QA</h2><p className="muted">Current blockers and warnings.</p></div></div><div className="action-list">{preview.checks.map((check, index) => (<div className="action-item" key={`${check.category}-${index}`}><StatusBadge label={check.severity} tone={check.severity === "Blocker" ? "danger" : "warning"} /><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>))}</div></section>
      </div>
    </Shell>
  );
}
