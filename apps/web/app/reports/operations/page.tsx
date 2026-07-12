import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { getAttendanceExceptions, getAttendanceReviews } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";

export default async function OperationalReportsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  const { periodStart, periodEnd } = currentCutoff();
  const [exceptions, reviews] = await Promise.all([getAttendanceExceptions(periodStart, periodEnd), getAttendanceReviews(periodStart, periodEnd)]);
  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const otPending = exceptions.filter((item) => item.ot_status === "Pending").length;

  return <Shell allowedRoles={["owner", "supervisor"]}><div className="page report-page">
    <header className="report-hero"><div><span className="eyebrow">Reports</span><h1>Operational reports</h1><p className="muted">Attendance exceptions and decisions for {periodStart} to {periodEnd}.</p></div><div className="report-actions"><Link className="button ghost" href="/attendance">Monthly compliance</Link><Link className="button" href="/attendance/review">Review queue</Link></div></header>
    <section className="report-kpis"><div className="report-kpi"><span>Open exceptions</span><strong>{exceptions.length}</strong><small>Current cutoff</small></div><div className="report-kpi"><span>Missing logs</span><strong>{missing}</strong><small>Incomplete time records</small></div><div className="report-kpi"><span>Absences</span><strong>{absent}</strong><small>Detected or classified</small></div><div className="report-kpi"><span>OT pending</span><strong>{otPending}</strong><small>Awaiting decision</small></div></section>
    <section className="report-grid"><article className="report-panel"><header><div><h2>Attendance summary</h2><p>Only unresolved exception rows remain in this report.</p></div><strong>{reviews.length} decisions</strong></header><div className="report-panel-body"><div className="table-wrap"><table className="system-table"><thead><tr><th>Date</th><th>Employee</th><th>Issue</th><th>In / Out</th><th>OT</th></tr></thead><tbody>{exceptions.map((item) => <tr key={item.id}><td>{item.work_date}</td><td><strong>{item.full_name}</strong></td><td>{item.is_absent ? "Absent" : item.attendance_status}</td><td>{item.actual_in || "—"} / {item.actual_out || "—"}</td><td>{item.ot_status || "None"}</td></tr>)}{exceptions.length === 0 ? <tr><td colSpan={5}>No open attendance items.</td></tr> : null}</tbody></table></div></div></article><article className="report-panel"><header><div><h2>Operations catalog</h2><p>Open the canonical source instead of duplicating workflows.</p></div></header><div className="report-panel-body report-catalog"><Link className="report-link" href="/schedule"><div><strong>Weekly schedule</strong><small>Published assignments, leave, and rest days</small></div><span>Open</span></Link><Link className="report-link" href="/schedule/requests"><div><strong>Shift requests</strong><small>Changes, swaps, and coverage decisions</small></div><span>Open</span></Link><Link className="report-link" href="/attendance/review"><div><strong>Attendance decisions</strong><small>Exception and overtime review</small></div><span>Open</span></Link><Link className="report-link" href="/performance-reviews"><div><strong>Performance reviews</strong><small>Review cycles and staff context</small></div><span>Open</span></Link></div></article></section>
  </div></Shell>;
}
