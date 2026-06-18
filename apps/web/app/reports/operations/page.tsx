import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { getAttendanceExceptions, getAttendanceReviews } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";

export default async function OperationalReportsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  }
  const { periodStart, periodEnd } = currentCutoff();
  const [exceptions, reviews] = await Promise.all([getAttendanceExceptions(periodStart, periodEnd), getAttendanceReviews(periodStart, periodEnd)]);
  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const otPending = exceptions.filter((item) => item.ot_status === "Pending").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Reports</span><h1>Operational reports</h1><p className="muted">{periodStart} to {periodEnd}</p></div></header>
        <section className="grid cols-4"><MetricCard label="Open exceptions" value={exceptions.length} /><MetricCard label="Missing logs" value={missing} /><MetricCard label="Absences" value={absent} /><MetricCard label="OT pending" value={otPending} /></section>
        <section className="card"><div className="panel-title"><div><h2>Attendance summary</h2><p className="muted">Supervisor-level exceptions.</p></div></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Issue</th><th>In / Out</th><th>OT</th></tr></thead><tbody>{exceptions.map((item) => <tr key={item.id}><td>{item.work_date}</td><td>{item.full_name}</td><td>{item.is_absent ? "Absent" : item.attendance_status}</td><td>{item.actual_in || "—"} / {item.actual_out || "—"}</td><td>{item.ot_status || "None"}</td></tr>)}{exceptions.length === 0 ? <tr><td colSpan={5}>No open attendance items.</td></tr> : null}</tbody></table></div><p className="muted" style={{ marginTop: 10 }}>{reviews.length} review decision(s) recorded for this cutoff.</p></section>
      </div>
    </Shell>
  );
}
