import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { HrRecordForm } from "@/components/HrRecordForm";
import { LeaveEntitlementForm } from "@/components/LeaveEntitlementForm";
import { LeaveRequestReview, type LeaveRequestItem } from "@/components/LeaveRequestReview";
import { currentSession } from "@/lib/session";

type Employee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };
type LeaveType = { id: number; name: string; default_credits: number; paid: number; active: number };
type LeaveBalance = { leave_type_id: number; leave_type_name: string; credits: number; used: number; remaining: number; entitled: number; paid: number; effective_start?: string | null; effective_end?: string | null };
type LeaveEmployee = Employee & { balances: LeaveBalance[] };
type LeaveBalanceResponse = { ok: boolean; year: number; leave_types: LeaveType[]; items: LeaveEmployee[] };
type HrRecord = { id: number; employee_id: number; employee_name: string; department?: string; position?: string; record_type: string; record_date: string; subject: string; details?: string | null; severity: string; status: string; issued_by?: string | null; rating?: number | null };

async function loadEmployees(): Promise<Employee[]> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/schedules/employees`, { headers: await backendHeaders(), cache: "no-store" });
  if (!res.ok) throw new Error("Employees could not be loaded.");
  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

async function loadLeaveBalances(): Promise<LeaveBalanceResponse> {
  const year = new Date().getFullYear();
  const res = await fetch(`${apiBaseUrl()}/api/v1/hr/leave-balances?year=${year}`, { headers: await backendHeaders(), cache: "no-store" });
  if (!res.ok) throw new Error("Leave balances could not be loaded.");
  const data = await res.json().catch(() => ({ ok: false, year, leave_types: [], items: [] }));
  return { ok: Boolean(data.ok), year: Number(data.year || year), leave_types: data.leave_types || [], items: data.items || [] };
}

async function loadHrRecords(): Promise<HrRecord[]> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/hr/records`, { headers: await backendHeaders(), cache: "no-store" });
  if (!res.ok) throw new Error("HR records could not be loaded.");
  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

async function loadLeaveRequests(): Promise<LeaveRequestItem[]> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/hr/leave-requests`, { headers: await backendHeaders(), cache: "no-store" });
  if (!res.ok) throw new Error("Leave requests could not be loaded.");
  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

function num(value: number | null | undefined) {
  return Number(value || 0).toLocaleString("en-PH", { maximumFractionDigits: 2 });
}

function entitlementWindow(balance: LeaveBalance) {
  if (balance.effective_start || balance.effective_end) return `${balance.effective_start || "—"} to ${balance.effective_end || "—"}`;
  return "Calendar year";
}

export default async function HrPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }
  const canCreate = ["owner", "payroll", "supervisor"].includes(session.role_key);
  const canManageEntitlements = ["owner", "payroll"].includes(session.role_key);
  const loaded = await Promise.allSettled([loadEmployees(), loadLeaveBalances(), loadHrRecords(), loadLeaveRequests()]);
  const failed = loaded.find((result) => result.status === "rejected");
  if (failed?.status === "rejected") {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page"><section className="card"><strong>HR data unavailable</strong><p className="muted">{failed.reason instanceof Error ? failed.reason.message : "Try again shortly."}</p></section></div></Shell>;
  }
  const [employees, leaveBalanceResponse, records, leaveRequests] = loaded.map((result) => result.status === "fulfilled" ? result.value : []) as [Employee[], LeaveBalanceResponse, HrRecord[], LeaveRequestItem[]];
  const leaveEmployees = leaveBalanceResponse.items || [];
  const leaveTypes = leaveBalanceResponse.leave_types || [];
  const infractions = records.filter((record) => record.record_type === "Infraction").length;
  const memos = records.filter((record) => record.record_type === "Memo").length;
  const pendingLeaves = leaveRequests.filter((item) => item.status === "Pending").length;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header"><div><span className="eyebrow">People</span><h1>HR records</h1><p className="muted">Formal records, leave approvals, and entitlement tracking.</p></div></header>
        <section className="grid cols-4"><div className="card"><strong>Formal records</strong><p>{records.length}</p></div><div className="card"><strong>Pending leaves</strong><p>{pendingLeaves}</p></div><div className="card"><strong>Infractions</strong><p>{infractions}</p></div><div className="card"><strong>Memos</strong><p>{memos}</p></div></section>
        <LeaveRequestReview items={leaveRequests} />
        <section className="grid cols-2">
          {canCreate ? <section className="card"><details><summary className="panel-title" style={{ cursor: "pointer", listStyle: "none" }}><div><h2>Add HR record</h2><p className="muted">Memo, infraction, or annual review.</p></div></summary><HrRecordForm employees={employees} /></details></section> : null}
          {canManageEntitlements ? <section className="card"><details><summary className="panel-title" style={{ cursor: "pointer", listStyle: "none" }}><div><h2>Set leave entitlement</h2><p className="muted">Credits, eligibility, and effective dates.</p></div></summary><LeaveEntitlementForm employees={employees} leaveTypes={leaveTypes} defaultYear={leaveBalanceResponse.year} /></details></section> : null}
        </section>
        <section className="card"><div className="panel-title"><div><h2>Leave balances</h2><p className="muted">Used leave is counted by the entitlement date window. Backdated records count when their leave dates fall inside the window.</p></div></div><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Department</th><th>Leave balances</th></tr></thead><tbody>{leaveEmployees.map((employee) => <tr key={employee.id}><td>{employee.full_name}</td><td>{employee.department || "—"}</td><td>{employee.balances.length ? employee.balances.map((b) => `${b.leave_type_name}: ${num(b.remaining)} left / ${num(b.credits)} credits · ${num(b.used)} used · ${entitlementWindow(b)}`).join("\n") : "No entitlement set"}</td></tr>)}{leaveEmployees.length === 0 ? <tr><td colSpan={3}>No leave balance records found.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><details><summary className="panel-title" style={{ cursor: "pointer", listStyle: "none" }}><div><h2>HR record timeline</h2><p className="muted">{records.length} records. Open for full history.</p></div></summary><div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Type</th><th>Subject</th><th>Severity</th><th>Status</th><th>Issued by</th></tr></thead><tbody>{records.map((record) => <tr key={record.id}><td>{record.record_date}</td><td>{record.employee_name}</td><td>{record.record_type}</td><td>{record.subject}{record.rating != null ? ` · Rating ${record.rating}` : ""}</td><td>{record.severity}</td><td>{record.status}</td><td>{record.issued_by || "—"}</td></tr>)}{records.length === 0 ? <tr><td colSpan={7}>No HR records yet.</td></tr> : null}</tbody></table></div></details></section>
      </div>
    </Shell>
  );
}
