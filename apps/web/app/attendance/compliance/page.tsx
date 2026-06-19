import Link from "next/link";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { AttendanceMemoForm } from "@/components/AttendanceMemoForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

function defaultMonth() {
  return new Date().toISOString().slice(0, 7);
}

function moveMonth(value: string, delta: number) {
  const [year, month] = value.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1 + delta, 1));
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

function numberText(value: unknown) {
  return Number(value || 0).toLocaleString("en-PH");
}

export default async function AttendanceCompliancePage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");

  if (!["owner", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  }

  const params = await searchParams;
  const month = params.month || defaultMonth();
  const data = await loadCompliance(month);
  const items = data.items || [];
  const memos = data.memos || [];
  const actionCount = items.filter((item: any) => item.handbook_action !== "No handbook action required").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Attendance Compliance</span>
            <h1>{month}</h1>
            <p className="muted">Monthly late, absence, AWOL, handbook action, and memo tracking.</p>
          </div>
          <StatusBadge label={actionCount ? `${actionCount} action needed` : "clear"} tone={actionCount ? "warning" : "ok"} />
        </header>

        <section className="badge-row">
          <Link className="primary-link" href={`/attendance/compliance?month=${moveMonth(month, -1)}`}>Previous month</Link>
          <Link className="primary-link" href={`/attendance/compliance?month=${moveMonth(month, 1)}`}>Next month</Link>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Monthly employee status</h2>
              <p className="muted">Late counts use the 5-minute grace rule. Over 30 minutes is also tracked as partial absence.</p>
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
                {items.map((item: any) => (
                  <tr key={item.employee_id}>
                    <td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code || "—"} · {item.department || "—"}</span></td>
                    <td>{numberText(item.scheduled_shifts)}</td>
                    <td>{numberText(item.missing_logs)}</td>
                    <td>{numberText(item.late_infractions)}</td>
                    <td>{numberText(item.partial_absences)}</td>
                    <td>{numberText(item.unexcused_absences)}</td>
                    <td>{numberText(item.awol)}</td>
                    <td>{numberText(item.approved_absences)}</td>
                    <td><strong>{item.handbook_action}</strong><br /><span className="muted">{item.attendance_reward_status}</span></td>
                    <td>
                      {item.handbook_action !== "No handbook action required" ? (
                        <AttendanceMemoForm employeeId={Number(item.employee_id)} employeeName={String(item.full_name || "Employee")} periodMonth={month} suggestedAction={String(item.handbook_action || "Attendance infraction")} />
                      ) : <span className="muted">—</span>}
                    </td>
                  </tr>
                ))}
                {items.length === 0 ? <tr><td colSpan={10}>No attendance records found for this month.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Memo history</h2>
              <p className="muted">Issued attendance memos for this month.</p>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Issued</th><th>Employee</th><th>Type</th><th>Level</th><th>Status</th><th>Reason</th><th>Notes</th></tr>
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
                {memos.length === 0 ? <tr><td colSpan={7}>No memos issued for this month.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
