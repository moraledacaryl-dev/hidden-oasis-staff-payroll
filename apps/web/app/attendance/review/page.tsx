import Link from "next/link";
import { redirect } from "next/navigation";
import { AttendanceDecisionPanel } from "@/components/AttendanceDecisionPanel";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";

export default async function AttendanceReviewPage({ searchParams }: { searchParams: Promise<{ start?: string; end?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;

  const params = await searchParams;
  const cutoff = currentCutoff();
  const start = params.start || cutoff.periodStart;
  const end = params.end || cutoff.periodEnd;
  const [exceptions, reviews] = await Promise.all([
    getAttendanceExceptions(start, end),
    getAttendanceReviews(start, end),
  ]);

  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const pendingOt = exceptions.filter((item) => item.ot_status === "Pending").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Attendance decisions</span>
            <h1>Employee-day review queue</h1>
            <p className="muted">Review actual logs, absences, and overtime one employee-day at a time before payroll.</p>
          </div>
          <div className="badge-row">
            <Link className="button secondary" href="/attendance">Monthly compliance</Link>
            <Link className="button" href="/schedule">Correct source records</Link>
          </div>
        </header>

        <form className="card form-panel" action="/attendance/review">
          <div className="form-grid">
            <label>Start<input name="start" type="date" defaultValue={start} /></label>
            <label>End<input name="end" type="date" defaultValue={end} /></label>
          </div>
          <div className="badge-row"><button className="button" type="submit">Load period</button></div>
        </form>

        <section className="grid cols-4">
          <div className="card"><strong>{exceptions.length}</strong><p className="muted">Open exceptions</p></div>
          <div className="card"><strong>{missing}</strong><p className="muted">Missing in or out</p></div>
          <div className="card"><strong>{absent}</strong><p className="muted">Absence records</p></div>
          <div className="card"><strong>{pendingOt}</strong><p className="muted">Pending overtime</p></div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div><h2>Decision queue</h2><p className="muted">{start} to {end}. Each action writes an attendance review record.</p></div>
            <StatusBadge label={exceptions.length ? `${exceptions.length} open` : "Clear"} tone={exceptions.length ? "warning" : "ok"} />
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Employee</th><th>Date</th><th>Actual</th><th>Attendance</th><th>Overtime</th><th>Notes</th><th>Decision</th></tr></thead>
              <tbody>
                {exceptions.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code} · {item.department || "—"}</span></td>
                    <td>{item.work_date}</td>
                    <td>{item.actual_in || "Missing"} → {item.actual_out || "Missing"}</td>
                    <td><StatusBadge label={item.is_absent ? item.absence_type || "Absent" : item.attendance_status || "Needs Review"} tone={item.is_absent ? "danger" : "warning"} /></td>
                    <td>{Number(item.detected_ot_hours || 0).toFixed(2)} h detected<br /><span className="muted">{item.ot_status || "None"}</span></td>
                    <td>{item.notes || "—"}</td>
                    <td><AttendanceDecisionPanel item={item} /></td>
                  </tr>
                ))}
                {exceptions.length === 0 ? <tr><td colSpan={7}>No attendance exceptions for this period.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Recent decisions</h2><p className="muted">Audit trail for the selected period.</p></div><StatusBadge label={`${reviews.length} decisions`} /></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Employee</th><th>Decision</th><th>Reviewer</th><th>Approved OT</th><th>Reason</th><th>Recorded</th></tr></thead>
              <tbody>{reviews.map((review) => <tr key={review.id}><td>{review.work_date}</td><td><strong>{review.full_name}</strong><br /><span className="muted">{review.employee_code}</span></td><td>{review.decision}</td><td>{review.reviewer}</td><td>{Number(review.approved_ot_hours || 0).toFixed(2)} h</td><td>{review.reason}</td><td>{review.created_at}</td></tr>)}{reviews.length === 0 ? <tr><td colSpan={7}>No decisions recorded for this period.</td></tr> : null}</tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
