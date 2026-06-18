import { redirect } from "next/navigation";
import { AttendanceDecisionButtons } from "@/components/AttendanceDecisionButtons";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews, numberText } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";

export default async function AttendanceReviewPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  }
  const { periodStart, periodEnd } = currentCutoff();
  const [exceptions, reviews] = await Promise.all([
    getAttendanceExceptions(periodStart, periodEnd),
    getAttendanceReviews(periodStart, periodEnd),
  ]);
  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const otPending = exceptions.filter((item) => item.ot_status === "Pending").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Attendance Review</span><h1>Supervisor action queue</h1><p className="muted">{periodStart} to {periodEnd}</p></div>
          <StatusBadge label={exceptions.length ? `${exceptions.length} open` : "clear"} tone={exceptions.length ? "warning" : "ok"} />
        </header>
        <section className="grid cols-4"><div className="card"><strong>{exceptions.length}</strong><p className="muted">Open exceptions</p></div><div className="card"><strong>{missing}</strong><p className="muted">Missing logs</p></div><div className="card"><strong>{absent}</strong><p className="muted">Absences</p></div><div className="card"><strong>{otPending}</strong><p className="muted">OT pending</p></div></section>
        <section className="card"><div className="panel-title"><div><h2>Exception queue</h2><p className="muted">Review attendance and OT exceptions.</p></div></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>In / Out</th><th>Attendance</th><th>Detected OT</th><th>Approved OT</th><th>OT status</th><th>Action</th></tr></thead><tbody>{exceptions.map((item) => (<tr key={item.id}><td>{item.work_date}</td><td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code} · {item.department || "—"}</span></td><td>{item.actual_in || "—"} / {item.actual_out || "—"}</td><td>{item.is_absent ? "Absent" : item.attendance_status}</td><td>{numberText(item.detected_ot_hours)}</td><td>{numberText(item.approved_ot_hours)}</td><td>{item.ot_status || "None"}</td><td><AttendanceDecisionButtons timeLogId={item.id} detectedOtHours={Number(item.detected_ot_hours || 0)} /></td></tr>))}{exceptions.length === 0 ? <tr><td colSpan={8}>No attendance exceptions for this cutoff.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><div className="panel-title"><div><h2>Review history</h2><p className="muted">Recent attendance decisions.</p></div></div><div className="table-wrap"><table><thead><tr><th>Reviewed</th><th>Employee</th><th>Date</th><th>Decision</th><th>Reviewer</th><th>Approved OT</th><th>Reason</th></tr></thead><tbody>{reviews.map((item) => (<tr key={item.id}><td>{item.created_at}</td><td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code} · {item.department || "—"}</span></td><td>{item.work_date}</td><td>{item.decision}</td><td>{item.reviewer}</td><td>{numberText(item.approved_ot_hours)}</td><td>{item.reason || "—"}</td></tr>))}{reviews.length === 0 ? <tr><td colSpan={7}>No attendance reviews recorded yet.</td></tr> : null}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
