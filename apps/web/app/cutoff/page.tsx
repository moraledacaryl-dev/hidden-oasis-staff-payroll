import { AttendanceDecisionButtons } from "@/components/AttendanceDecisionButtons";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews, getPayrollPreview, numberText, peso } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function CutoffPage() {
  const [preview, exceptions, reviews] = await Promise.all([
    getPayrollPreview(DEFAULT_START, DEFAULT_END),
    getAttendanceExceptions(DEFAULT_START, DEFAULT_END),
    getAttendanceReviews(DEFAULT_START, DEFAULT_END),
  ]);
  const blockers = preview.checks.filter((check) => check.severity === "Blocker");
  const ready = blockers.length === 0 && exceptions.length === 0;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Cutoff Control</span><h1>{DEFAULT_START} to {DEFAULT_END}</h1><p className="muted">One readiness cockpit before payroll approval. Preview only.</p></div>
          <StatusBadge label={ready ? "ready" : "not ready"} tone={ready ? "success" : "warning"} />
        </header>
        <section className="grid cols-4"><MetricCard label="Net payroll" value={peso(preview.totals.net_pay)} detail="Preview only" /><MetricCard label="Blockers" value={String(blockers.length)} detail="Must be zero" /><MetricCard label="Exceptions" value={String(exceptions.length)} detail="Attendance queue" /><MetricCard label="Reviews" value={String(reviews.length)} detail="Audit records" /></section>
        <section className="card"><div className="panel-title"><div><h2>Immediate attendance actions</h2><p className="muted">Top exceptions from the supervisor queue.</p></div></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Status</th><th>OT</th><th>Action</th></tr></thead><tbody>{exceptions.slice(0, 10).map((item) => (<tr key={item.id}><td>{item.work_date}</td><td>{item.full_name}</td><td>{item.is_absent ? "Absent" : item.attendance_status}</td><td>{numberText(item.detected_ot_hours)}</td><td><AttendanceDecisionButtons timeLogId={item.id} detectedOtHours={Number(item.detected_ot_hours || 0)} /></td></tr>))}{exceptions.length === 0 ? <tr><td colSpan={5}>No attendance exceptions.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><div className="panel-title"><div><h2>Payroll QA</h2><p className="muted">Current blockers and warnings.</p></div></div><div className="action-list">{preview.checks.map((check, index) => (<div className="action-item" key={`${check.category}-${index}`}><StatusBadge label={check.severity} tone={check.severity === "Blocker" ? "danger" : "warning"} /><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>))}</div></section>
      </div>
    </Shell>
  );
}
