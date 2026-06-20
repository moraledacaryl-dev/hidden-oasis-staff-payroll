import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { HrRecordForm } from "@/components/HrRecordForm";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function apiHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

type Employee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };
type LeaveBalance = { leave_type_id: number; leave_type_name: string; credits: number; used: number; remaining: number; entitled: number; paid: number };
type LeaveEmployee = Employee & { balances: LeaveBalance[] };
type HrRecord = { id: number; employee_id: number; employee_name: string; department?: string; position?: string; record_type: string; record_date: string; subject: string; details?: string | null; severity: string; status: string; issued_by?: string | null; rating?: number | null };

async function loadEmployees(): Promise<Employee[]> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/schedules/employees`, { headers: await apiHeaders(), cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

async function loadLeaveBalances(): Promise<LeaveEmployee[]> {
  const year = new Date().getFullYear();
  const res = await fetch(`${apiBaseUrl()}/api/v1/hr/leave-balances?year=${year}`, { headers: await apiHeaders(), cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

async function loadHrRecords(): Promise<HrRecord[]> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/hr/records`, { headers: await apiHeaders(), cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

function num(value: number | null | undefined) {
  return Number(value || 0).toLocaleString("en-PH", { maximumFractionDigits: 2 });
}

export default async function HrPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor", "staff"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor", "staff"]}><div /></Shell>;
  }
  const canCreate = ["owner", "payroll", "supervisor"].includes(session.role_key);
  const [employees, leaveEmployees, records] = await Promise.all([loadEmployees(), loadLeaveBalances(), loadHrRecords()]);
  const annualReviews = records.filter((record) => record.record_type === "Annual Review").length;
  const infractions = records.filter((record) => record.record_type === "Infraction").length;
  const memos = records.filter((record) => record.record_type === "Memo").length;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor", "staff"]}>
      <div className="page">
        <header className="page-header">
          <div>
            <span className="eyebrow">HR Records</span>
            <h1>Leave and formal records</h1>
            <p className="muted">Leave balances and formal HR records. Annual performance reviews are handled separately.</p>
          </div>
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>Formal records</strong><p>{records.length}</p></div>
          <div className="card"><strong>Infractions</strong><p>{infractions}</p></div>
          <div className="card"><strong>Memos</strong><p>{memos}</p></div>
        </section>

        {canCreate ? <section className="card"><div className="panel-title"><div><h2>Add formal HR record</h2><p className="muted">Create infraction, memo, leave note, or HR document. Use Performance Reviews for annual reviews.</p></div></div><HrRecordForm employees={employees} /></section> : null}

        <section className="card">
          <div className="panel-title"><div><h2>Leave balances</h2><p className="muted">Credits, used leave, and remaining leave by employee.</p></div></div>
          <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Department</th><th>Leave balances</th></tr></thead><tbody>
            {leaveEmployees.map((employee) => <tr key={employee.id}><td>{employee.full_name}</td><td>{employee.department || "—"}</td><td>{employee.balances.length ? employee.balances.map((b) => `${b.leave_type_name}: ${num(b.remaining)} remaining / ${num(b.credits)} credits`).join(" · ") : "No entitlement set"}</td></tr>)}
            {leaveEmployees.length === 0 ? <tr><td colSpan={3}>No leave balance records found.</td></tr> : null}
          </tbody></table></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>HR record timeline</h2><p className="muted">Newest records first.</p></div></div>
          <div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Type</th><th>Subject</th><th>Severity</th><th>Status</th><th>Issued by</th></tr></thead><tbody>
            {records.map((record) => <tr key={record.id}><td>{record.record_date}</td><td>{record.employee_name}</td><td>{record.record_type}</td><td>{record.subject}{record.rating != null ? ` · Rating ${record.rating}` : ""}</td><td>{record.severity}</td><td>{record.status}</td><td>{record.issued_by || "—"}</td></tr>)}
            {records.length === 0 ? <tr><td colSpan={7}>No HR records yet.</td></tr> : null}
          </tbody></table></div>
        </section>
      </div>
    </Shell>
  );
}
