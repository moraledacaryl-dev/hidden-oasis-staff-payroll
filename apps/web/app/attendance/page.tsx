import Link from "next/link";
import { redirect } from "next/navigation";
import { AttendanceMemoForm } from "@/components/AttendanceMemoForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, backendHeaders } from "@/lib/api";
import { currentSession } from "@/lib/session";

type LateDetail = { date: string; actual_in: string; scheduled_start: string; minutes_late: number; status: string };
type AbsenceDetail = { date: string; type: string };
type ComplianceItem = {
  employee_id: number;
  full_name: string;
  employee_code?: string;
  department?: string;
  scheduled_shifts?: number;
  missing_logs?: number;
  grace_periods?: number;
  late_infractions?: number;
  partial_absences?: number;
  approved_absences?: number;
  unexcused_absences?: number;
  awol?: number;
  late_details?: LateDetail[];
  absence_details?: AbsenceDetail[];
  handbook_action: string;
  attendance_reward_status?: string;
};
type AttendanceMemo = { id: number; issued_at?: string; created_at?: string; full_name?: string; employee_code?: string; department?: string; memo_type: string; memo_level: string; status: string; reason: string; notes?: string };
type ComplianceResponse = { ok: boolean; items: ComplianceItem[]; memos: AttendanceMemo[]; error?: string };
type PerformanceMonth = ComplianceItem & { month: string };
type PerformanceResponse = { employee?: { full_name?: string }; totals?: Partial<ComplianceItem>; months: PerformanceMonth[] };

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

async function loadCompliance(month: string): Promise<ComplianceResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/compliance?month=${month}`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    return { ok: false, items: [], memos: [], error: `Attendance API failed ${response.status}: ${text}` };
  }
  return response.json() as Promise<ComplianceResponse>;
}

async function loadPerformance(employeeId: string): Promise<PerformanceResponse | null> {
  if (!employeeId) return null;
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/performance?employee_id=${employeeId}&months=12`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  if (!response.ok) return null;
  return response.json() as Promise<PerformanceResponse>;
}

export default async function AttendancePage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string; employee?: string; employee_id?: string }>;
}) {
  const session = await currentSession();
  if (!session) redirect("/login");

  if (!["owner", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  }

  const params = await searchParams;
  const month = params.month || defaultMonth();
  const employeeFilter = (params.employee || "").trim().toLowerCase();
  const employeeId = params.employee_id || "";
  const { periodStart, periodEnd } = monthBounds(month);

  const [compliance, performance] = await Promise.all([
    loadCompliance(month),
    loadPerformance(employeeId),
  ]);

  const complianceItems = (compliance.items || []).filter((item) => {
    if (!employeeFilter) return true;
    return String(item.full_name || "").toLowerCase().includes(employeeFilter);
  });

  const memos = compliance.memos || [];
  const lateCount = complianceItems.reduce((sum, item) => sum + Number(item.late_infractions || 0), 0);
  const graceCount = complianceItems.reduce((sum, item) => sum + Number(item.grace_periods || 0), 0);
  const partialCount = complianceItems.reduce((sum, item) => sum + Number(item.partial_absences || 0), 0);
  const absenceCount = complianceItems.reduce((sum, item) => sum + Number(item.approved_absences || 0) + Number(item.unexcused_absences || 0) + Number(item.awol || 0), 0);
  const actionCount = complianceItems.filter((item) => item.handbook_action !== "No action required").length;
  const employeeOptions = Array.from(new Map((compliance.items || []).map((item) => [item.employee_id, item])).values()).sort((a, b) => a.full_name.localeCompare(b.full_name));

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Attendance</span>
            <h1>{month}</h1>
          </div>
          <StatusBadge label={actionCount ? `${actionCount} action needed` : "clear"} tone={actionCount ? "warning" : "ok"} />
        </header>

        <section className="badge-row">
          <Link className="primary-link" href={`/attendance?month=${moveMonth(month, -1)}`}>Previous month</Link>
          <Link className="primary-link" href={`/attendance?month=${moveMonth(month, 1)}`}>Next month</Link>
          <Link className="primary-link" href={`/attendance?month=${defaultMonth()}`}>Current month</Link>
          <Link className="primary-link" href="/schedule">Correct logs in Schedule</Link>
        </section>

        <form className="card" action="/attendance">
          <div className="form-grid">
            <label>Month<input name="month" type="month" defaultValue={month} /></label>
            <label>Staff search<input name="employee" placeholder="Search employee name" defaultValue={params.employee || ""} /></label>
            <label>12-month history<select name="employee_id" defaultValue={employeeId}><option value="">Select employee</option>{employeeOptions.map((item) => <option key={item.employee_id} value={item.employee_id}>{item.full_name}</option>)}</select></label>
          </div>
          <div className="badge-row"><button className="primary-button" type="submit">View attendance</button></div>
        </form>

        {!compliance.ok ? (
          <section className="card">
            <strong>Attendance data did not load.</strong>
            <p className="muted">{compliance.error || "The compliance API returned an error."}</p>
          </section>
        ) : null}

        <section className="grid cols-4">
          <div className="card"><strong>{lateCount}</strong><p className="muted">Late infractions</p></div>
          <div className="card"><strong>{graceCount}</strong><p className="muted">Grace periods</p></div>
          <div className="card"><strong>{partialCount}</strong><p className="muted">Partial absences</p></div>
          <div className="card"><strong>{absenceCount}</strong><p className="muted">Absences / leaves / AWOL</p></div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Monthly Compliance</h2>
              <p className="muted">{periodStart} to {periodEnd}. Lates are computed from scheduled start versus actual in.</p>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Scheduled</th>
                  <th>Missing</th>
                  <th>Grace</th>
                  <th>Lates</th>
                  <th>Partial</th>
                  <th>Absences</th>
                  <th>Details</th>
                  <th>Handbook action</th>
                  <th>Memo</th>
                </tr>
              </thead>
              <tbody>
                {complianceItems.map((item) => (
                  <tr key={item.employee_id}>
                    <td>
                      <strong>{item.full_name}</strong>
                      <br />
                      <span className="muted">{item.employee_code || "—"} · {item.department || "—"} · ID {item.employee_id}</span>
                    </td>
                    <td>{Number(item.scheduled_shifts || 0)}</td>
                    <td>{Number(item.missing_logs || 0)}</td>
                    <td>{Number(item.grace_periods || 0)}</td>
                    <td>{Number(item.late_infractions || 0)}</td>
                    <td>{Number(item.partial_absences || 0)}</td>
                    <td>
                      Approved: {Number(item.approved_absences || 0)}
                      <br />Unexcused: {Number(item.unexcused_absences || 0)}
                      <br />AWOL: {Number(item.awol || 0)}
                    </td>
                    <td>
                      {(item.late_details || []).length ? (
                        <div>
                          <strong>Lates</strong>
                          {(item.late_details || []).map((late) => (
                            <div key={`${late.date}-${late.actual_in}`} className="muted">
                              {late.date}: {late.scheduled_start} → {late.actual_in} ({late.minutes_late} min, {late.status})
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {(item.absence_details || []).length ? (
                        <div>
                          <strong>Absences</strong>
                          {(item.absence_details || []).map((absence) => (
                            <div key={`${absence.date}-${absence.type}`} className="muted">
                              {absence.date}: {absence.type}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {!(item.late_details || []).length && !(item.absence_details || []).length ? <span className="muted">—</span> : null}
                    </td>
                    <td>
                      <strong>{item.handbook_action}</strong>
                      <br />
                      <span className="muted">{item.attendance_reward_status}</span>
                    </td>
                    <td>
                      {item.handbook_action !== "No action required" ? (
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

        {performance ? (
          <section className="card">
            <div className="panel-title">
              <div>
                <h2>12-Month Staff Performance</h2>
                <p className="muted">{performance.employee?.full_name || "Selected employee"}</p>
              </div>
            </div>
            <section className="grid cols-4">
              <div className="action-item"><strong>{performance.totals?.late_infractions || 0}</strong><p className="muted">Total lates</p></div>
              <div className="action-item"><strong>{performance.totals?.grace_periods || 0}</strong><p className="muted">Grace periods</p></div>
              <div className="action-item"><strong>{performance.totals?.unexcused_absences || 0}</strong><p className="muted">Unexcused absences</p></div>
              <div className="action-item"><strong>{performance.totals?.awol || 0}</strong><p className="muted">AWOL</p></div>
            </section>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Month</th><th>Scheduled</th><th>Missing</th><th>Grace</th><th>Lates</th><th>Partial</th><th>Unexcused</th><th>AWOL</th><th>Approved</th><th>Action</th></tr></thead>
                <tbody>
                  {(performance.months || []).map((row) => (
                    <tr key={row.month}>
                      <td>{row.month}</td>
                      <td>{row.scheduled_shifts}</td>
                      <td>{row.missing_logs}</td>
                      <td>{row.grace_periods}</td>
                      <td>{row.late_infractions}</td>
                      <td>{row.partial_absences}</td>
                      <td>{row.unexcused_absences}</td>
                      <td>{row.awol}</td>
                      <td>{row.approved_absences}</td>
                      <td>{row.handbook_action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Memo History</h2>
              <p className="muted">Attendance memos issued for the selected month.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Issued</th><th>Employee</th><th>Type</th><th>Level</th><th>Status</th><th>Reason</th><th>Notes</th></tr></thead>
              <tbody>
                {memos.map((memo) => (
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
      </div>
    </Shell>
  );
}
