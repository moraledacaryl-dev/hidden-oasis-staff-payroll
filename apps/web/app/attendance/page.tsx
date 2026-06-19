import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { AttendanceDecisionButtons } from "@/components/AttendanceDecisionButtons";
import { AttendanceMemoForm } from "@/components/AttendanceMemoForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, getAttendanceExceptions, getAttendanceReviews, numberText } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

function defaultMonth() {
  return new Date().toISOString().slice(0, 7);
}

function monthBounds(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const start = new Date(Date.UTC(year, monthNumber - 1, 1));
  const end = new Date(Date.UTC(year, monthNumber, 0));
  return {
    periodStart: start.toISOString().slice(0, 10),
    periodEnd: end.toISOString().slice(0, 10),
  };
}

function moveMonth(value: string, delta: number) {
  const [year, monthNumber] = value.split("-").map(Number);
  const next = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
  return next.toISOString().slice(0, 7);
}

async function authHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

async function loadCompliance(month: string) {
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/compliance?month=${month}`, {
    headers: await authHeaders(),
    cache: "no-store",
  });
  if (!response.ok) return { ok: false, items: [], memos: [] };
  return response.json();
}

export default async function AttendancePage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string; employee?: string }>;
}) {
  const session = await currentSession();
  if (!session) redirect("/login");

  if (!["owner", "supervisor"].includes(session.role_key)) {
    return (
      <Shell allowedRoles={["owner", "supervisor"]}>
        <div />
      </Shell>
    );
  }

  const params = await searchParams;
  const month = params.month || defaultMonth();
  const employeeFilter = (params.employee || "").trim().toLowerCase();
  const { periodStart, periodEnd } = monthBounds(month);

  const [exceptions, reviews, compliance] = await Promise.all([
    getAttendanceExceptions(periodStart, periodEnd),
    getAttendanceReviews(periodStart, periodEnd),
    loadCompliance(month),
  ]);

  const complianceItems = (compliance.items || []).filter((item: any) => {
    if (!employeeFilter) return true;
    return String(item.full_name || "").toLowerCase().includes(employeeFilter);
  });
  const memos = compliance.memos || [];

  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const otPending = exceptions.filter((item) => item.ot_status === "Pending").length;
  const lateCount = complianceItems.reduce((sum: number, item: any) => sum + Number(item.late_infractions || 0), 0);
  const partialCount = complianceItems.reduce((sum: number, item: any) => sum + Number(item.partial_absences || 0), 0);
  const unexcusedCount = complianceItems.reduce((sum: number, item: any) => sum + Number(item.unexcused_absences || 0), 0);
  const awolCount = complianceItems.reduce((sum: number, item: any) => sum + Number(item.awol || 0), 0);
  const actionCount = complianceItems.filter((item: any) => item.handbook_action !== "No handbook action required").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Attendance</span>
            <h1>{month}</h1>
            <p className="muted">Monthly attendance review, compliance, memo actions, and past performance.</p>
          </div>
          <StatusBadge label={actionCount ? `${actionCount} action needed` : "clear"} tone={actionCount ? "warning" : "ok"} />
        </header>

        <section className="badge-row">
          <Link className="primary-link" href={`/attendance?month=${moveMonth(month, -1)}`}>Previous month</Link>
          <Link className="primary-link" href={`/attendance?month=${moveMonth(month, 1)}`}>Next month</Link>
          <Link className="primary-link" href={`/attendance?month=${defaultMonth()}`}>Current month</Link>
        </section>

        <form className="card" action="/attendance">
          <div className="form-grid">
            <label>
              Month
              <input name="month" type="month" defaultValue={month} />
            </label>
            <label>
              Staff search
              <input name="employee" placeholder="Search employee name" defaultValue={params.employee || ""} />
            </label>
          </div>
          <div className="badge-row">
            <button className="primary-button" type="submit">View attendance</button>
          </div>
        </form>

        <section className="grid cols-4">
          <div className="card"><strong>{exceptions.length}</strong><p className="muted">Daily review items</p></div>
          <div className="card"><strong>{lateCount}</strong><p className="muted">Late infractions</p></div>
          <div className="card"><strong>{partialCount}</strong><p className="muted">Partial absences</p></div>
          <div className="card"><strong>{unexcusedCount + awolCount}</strong><p className="muted">Unexcused / AWOL</p></div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Daily Review</h2>
              <p className="muted">{periodStart} to {periodEnd}. Missing logs, absences, and OT exceptions for supervisor action.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Employee</th>
                  <th>In / Out</th>
                  <th>Attendance</th>
                  <th>Detected OT</th>
                  <th>Approved OT</th>
                  <th>OT status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {exceptions.map((item) => (
                  <tr key={item.id}>
                    <td>{item.work_date}</td>
                    <td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code} · {item.department || "—"}</span></td>
                    <td>{item.actual_in || "—"} / {item.actual_out || "—"}</td>
                    <td>{item.is_absent ? "Absent" : item.attendance_status}</td>
                    <td>{numberText(item.detected_ot_hours)}</td>
                    <td>{numberText(item.approved_ot_hours)}</td>
                    <td>{item.ot_status || "None"}</td>
                    <td><AttendanceDecisionButtons timeLogId={item.id} detectedOtHours={Number(item.detected_ot_hours || 0)} /></td>
                  </tr>
                ))}
                {exceptions.length === 0 ? <tr><td colSpan={8}>No daily attendance exceptions for this month.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Monthly Compliance / Past Performance</h2>
              <p className="muted">Counts are based on the calendar month. Lates use scheduled start versus actual in.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Scheduled</th>
                  <th>Missing</th>
                  <th>Lates</th>
                  <th>Partial</th>
                  <th>Unexcused</th>
                  <th>AWOL</th>
                  <th>Approved</th>
                  <th>Handbook action</th>
                  <th>Memo</th>
                </tr>
              </thead>
              <tbody>
                {complianceItems.map((item: any) => (
                  <tr key={item.employee_id}>
                    <td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code || "—"} · {item.department || "—"}</span></td>
                    <td>{Number(item.scheduled_shifts || 0)}</td>
                    <td>{Number(item.missing_logs || 0)}</td>
                    <td>{Number(item.late_infractions || 0)}</td>
                    <td>{Number(item.partial_absences || 0)}</td>
                    <td>{Number(item.unexcused_absences || 0)}</td>
                    <td>{Number(item.awol || 0)}</td>
                    <td>{Number(item.approved_absences || 0)}</td>
                    <td><strong>{item.handbook_action}</strong><br /><span className="muted">{item.attendance_reward_status}</span></td>
                    <td>
                      {item.handbook_action !== "No handbook action required" ? (
                        <AttendanceMemoForm
                          employeeId={Number(item.employee_id)}
                          employeeName={String(item.full_name || "Employee")}
                          periodMonth={month}
                          suggestedAction={String(item.handbook_action || "Attendance infraction")}
                        />
                      ) : <span className="muted">—</span>}
                    </td>
                  </tr>
                ))}
                {complianceItems.length === 0 ? <tr><td colSpan={10}>No monthly attendance records found.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Memo History</h2>
              <p className="muted">Attendance memos issued for the selected month.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Issued</th>
                  <th>Employee</th>
                  <th>Type</th>
                  <th>Level</th>
                  <th>Status</th>
                  <th>Reason</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {memos.map((memo: any) => (
                  <tr key={memo.id}>
                    <td>{memo.issued_at || memo.created_at || "—"}</td>
                    <td><strong>{memo.full_name || "—"}</strong><br /><span className="muted">{memo.employee_code || "—"} · {memo.department || "—"}</span></td>
                    <td>{memo.memo_type}</td>
                    <td>{memo.memo_level}</td>
                    <td>{memo.status}</td>
                    <td>{memo.reason}</td>
                    <td>{memo.notes || "—"}</td>
                  </tr>
                ))}
                {memos.length === 0 ? <tr><td colSpan={7}>No attendance memos for this month.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Review History</h2>
              <p className="muted">Recent attendance/OT decisions for the selected month.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Reviewed</th>
                  <th>Employee</th>
                  <th>Date</th>
                  <th>Decision</th>
                  <th>Reviewer</th>
                  <th>Approved OT</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {reviews.map((item) => (
                  <tr key={item.id}>
                    <td>{item.created_at}</td>
                    <td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code} · {item.department || "—"}</span></td>
                    <td>{item.work_date}</td>
                    <td>{item.decision}</td>
                    <td>{item.reviewer}</td>
                    <td>{numberText(item.approved_ot_hours)}</td>
                    <td>{item.reason || "—"}</td>
                  </tr>
                ))}
                {reviews.length === 0 ? <tr><td colSpan={7}>No attendance reviews recorded for this month.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
