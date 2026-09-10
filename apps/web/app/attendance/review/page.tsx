import Link from "next/link";
import { redirect } from "next/navigation";
import { AttendanceDecisionPanel } from "@/components/AttendanceDecisionPanel";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { MetricCard, MetricGrid, PageHeading, SectionBody, SectionCard, SectionHeader, Toolbar } from "@/components/UiPrimitives";
import { getAttendanceExceptions, getAttendanceReviews } from "@/lib/api";
import { currentCutoff, mondayOfWeek, formatBusinessDateTime } from "@/lib/period";
import { currentSession } from "@/lib/session";

export default async function AttendanceReviewPage({ searchParams }: { searchParams: Promise<{ start?: string; end?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;

  const params = await searchParams;
  const cutoff = currentCutoff();
  const start = params.start || cutoff.periodStart;
  const end = params.end || cutoff.periodEnd;
  const [exceptions, reviews] = await Promise.all([getAttendanceExceptions(start, end), getAttendanceReviews(start, end)]);
  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const pendingOt = exceptions.filter((item) => item.ot_status === "Pending").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <PageHeading
          eyebrow="Attendance decisions"
          title="Employee-day review queue"
          description="Review actual logs, absences, and overtime one employee-day at a time before payroll."
          actions={<div className="operations-tabs"><Link href={`/attendance/review?start=${start}&end=${end}`} aria-current="page">Review queue</Link><Link href="/attendance">Monthly compliance</Link><Link href="/schedule/import">Upload logs</Link></div>}
        />

        <SectionCard>
          <Toolbar>
            <form className="form-grid" action="/attendance/review">
              <label>Start<input name="start" type="date" defaultValue={start} /></label>
              <label>End<input name="end" type="date" defaultValue={end} /></label>
              <button className="button" type="submit">Load period</button><Link className="button secondary" href="/attendance/review">Reset</Link>
            </form>
            <Link className="button secondary" href={`/schedule?week_start=${mondayOfWeek(start)}`}>Correct source records</Link>
          </Toolbar>
        </SectionCard>

        <MetricGrid>
          <MetricCard value={exceptions.length} label="Open exceptions" />
          <MetricCard value={missing} label="Missing in or out" />
          <MetricCard value={absent} label="Absence records" />
          <MetricCard value={pendingOt} label="Pending overtime" />
        </MetricGrid>

        <SectionCard>
          <SectionHeader title="Decision queue" description={`${start} to ${end}. Each action writes an attendance review record.`} actions={<StatusBadge label={exceptions.length ? `${exceptions.length} open` : "Clear"} tone={exceptions.length ? "warning" : "ok"} />} />
          <SectionBody flush>
            <div className="table-wrap"><table className="responsive-records "><thead><tr><th>Employee</th><th>Date</th><th>Actual</th><th>Detected issue</th><th>Overtime</th><th>Notes</th><th>Decision</th></tr></thead><tbody>
              {exceptions.map((item) => <tr key={item.id}><td data-label="Employee"><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code} · {item.department || "—"}</span></td><td data-label="Date">{item.work_date}</td><td data-label="Actual">{item.actual_in || "Missing"} → {item.actual_out || "Missing"}</td><td data-label="Detected issue"><StatusBadge label={item.is_absent ? item.absence_type || "Absent" : item.attendance_status || "Needs Review"} tone={item.is_absent ? "danger" : "warning"} /></td><td data-label="Overtime">{Number(item.detected_ot_hours || 0).toFixed(2)} h detected<br /><span className="muted">{item.ot_status || "None"}</span></td><td data-label="Notes">{item.notes || "—"}</td><td data-label="Decision"><AttendanceDecisionPanel item={item} /></td></tr>)}
              {exceptions.length === 0 ? <tr><td colSpan={7}>No attendance exceptions for this period.</td></tr> : null}
            </tbody></table></div>
          </SectionBody>
        </SectionCard>

        <SectionCard>
          <SectionHeader title="Recent decisions" description="Audit trail for the selected period." actions={<StatusBadge label={`${reviews.length} decisions`} />} />
          <SectionBody flush><div className="table-wrap"><table className="responsive-records "><thead><tr><th>Date</th><th>Employee</th><th>Decision</th><th>Reviewer</th><th>Approved OT</th><th>Reason</th><th>Recorded</th></tr></thead><tbody>{reviews.map((review) => <tr key={review.id}><td data-label="Date">{review.work_date}</td><td data-label="Employee"><strong>{review.full_name}</strong><br /><span className="muted">{review.employee_code}</span></td><td data-label="Decision">{review.decision}</td><td data-label="Reviewer">{review.reviewer}</td><td data-label="Approved OT">{Number(review.approved_ot_hours || 0).toFixed(2)} h</td><td data-label="Reason">{review.reason}</td><td data-label="Recorded">{formatBusinessDateTime(review.created_at)}</td></tr>)}{reviews.length === 0 ? <tr><td colSpan={7}>No decisions recorded for this period.</td></tr> : null}</tbody></table></div></SectionBody>
        </SectionCard>
      </div>
    </Shell>
  );
}
