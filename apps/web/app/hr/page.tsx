import Link from "next/link";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { HrRecordForm } from "@/components/HrRecordForm";
import { LeaveEntitlementForm } from "@/components/LeaveEntitlementForm";
import { LeaveRequestReview, type LeaveRequestItem } from "@/components/LeaveRequestReview";
import { PageHeading, SectionBody, SectionCard, SectionHeader } from "@/components/UiPrimitives";
import { currentSession } from "@/lib/session";

type Employee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };
type LeaveType = { id: number; name: string; default_credits: number; paid: number; active: number };
type LeaveBalance = { leave_type_id: number; leave_type_name: string; credits: number; used: number; remaining: number; entitled: number; paid: number; effective_start?: string | null; effective_end?: string | null };
type LeaveEmployee = Employee & { balances: LeaveBalance[] };
type LeaveBalanceResponse = { ok: boolean; year: number; leave_types: LeaveType[]; items: LeaveEmployee[] };
type HrRecord = { id: number; employee_id: number; employee_name: string; department?: string; position?: string; record_type: string; record_date: string; subject: string; details?: string | null; severity: string; status: string; issued_by?: string | null; rating?: number | null };

async function loadEmployees(): Promise<Employee[]> { const res = await fetch(`${apiBaseUrl()}/api/v1/schedules/employees`, { headers: await backendHeaders(), cache: "no-store" }); if (!res.ok) throw new Error("Employees could not be loaded."); const data = await res.json().catch(() => ({ items: [] })); return data.items || []; }
async function loadLeaveBalances(): Promise<LeaveBalanceResponse> { const year = new Date().getFullYear(); const res = await fetch(`${apiBaseUrl()}/api/v1/hr/leave-balances?year=${year}`, { headers: await backendHeaders(), cache: "no-store" }); if (!res.ok) throw new Error("Leave balances could not be loaded."); const data = await res.json().catch(() => ({ ok: false, year, leave_types: [], items: [] })); return { ok: Boolean(data.ok), year: Number(data.year || year), leave_types: data.leave_types || [], items: data.items || [] }; }
async function loadHrRecords(): Promise<HrRecord[]> { const res = await fetch(`${apiBaseUrl()}/api/v1/hr/records`, { headers: await backendHeaders(), cache: "no-store" }); if (!res.ok) throw new Error("HR records could not be loaded."); const data = await res.json().catch(() => ({ items: [] })); return data.items || []; }
async function loadLeaveRequests(): Promise<LeaveRequestItem[]> { const res = await fetch(`${apiBaseUrl()}/api/v1/hr/leave-requests`, { headers: await backendHeaders(), cache: "no-store" }); if (!res.ok) throw new Error("Leave requests could not be loaded."); const data = await res.json().catch(() => ({ items: [] })); return data.items || []; }
function num(value: number | null | undefined) { return Number(value || 0).toLocaleString("en-PH", { maximumFractionDigits: 2 }); }
function entitlementWindow(balance: LeaveBalance) { return balance.effective_start || balance.effective_end ? `${balance.effective_start || "—"} to ${balance.effective_end || "—"}` : "Calendar year"; }

export default async function HrPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  const canCreate = ["owner", "payroll", "supervisor"].includes(session.role_key);
  const canManageEntitlements = ["owner", "payroll"].includes(session.role_key);
  const loaded = await Promise.allSettled([loadEmployees(), loadLeaveBalances(), loadHrRecords(), loadLeaveRequests()]);
  const failed = loaded.find((result) => result.status === "rejected");
  if (failed?.status === "rejected") return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page"><section className="card"><strong>HR data unavailable</strong><p className="muted">{failed.reason instanceof Error ? failed.reason.message : "Try again shortly."}</p></section></div></Shell>;
  const [employees, leaveBalanceResponse, records, leaveRequests] = loaded.map((result) => result.status === "fulfilled" ? result.value : []) as [Employee[], LeaveBalanceResponse, HrRecord[], LeaveRequestItem[]];
  const leaveEmployees = leaveBalanceResponse.items || [];
  const leaveTypes = leaveBalanceResponse.leave_types || [];
  const pendingLeaves = leaveRequests.filter((item) => item.status === "Pending").length;
  const activeEntitlements = leaveEmployees.reduce((sum, employee) => sum + employee.balances.length, 0);
  const openRecords = records.filter((record) => !["Closed", "Resolved", "Finalized"].includes(record.status)).length;
  const annualReviews = records.filter((record) => record.record_type === "Annual Review").length;

  return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page people-page">
    <PageHeading eyebrow="People" title="HR and leave" description="Manage leave requests, employee entitlements, formal records, and long-term people history." actions={<><Link className="button secondary" href="/staff">Staff directory</Link><Link className="button secondary" href="/performance-reviews">Performance reviews</Link></>} />
    <section className="people-kpis"><div className="people-kpi"><span>Pending leave requests</span><strong>{pendingLeaves}</strong></div><div className="people-kpi"><span>Active entitlements</span><strong>{activeEntitlements}</strong></div><div className="people-kpi"><span>Open formal records</span><strong>{openRecords}</strong></div><div className="people-kpi"><span>Annual reviews recorded</span><strong>{annualReviews}</strong></div></section>

    <div className="hr-overview">
      <div className="hr-stack">
        <SectionCard><SectionHeader title="Leave request queue" description="Review current leave requests before they affect published schedules and payroll." actions={<StatusBadge label={pendingLeaves ? `${pendingLeaves} pending` : "Clear"} tone={pendingLeaves ? "warning" : "ok"} />} /><SectionBody><LeaveRequestReview items={leaveRequests} /></SectionBody></SectionCard>
        <section className="hr-panel"><header><div><h2>Leave balances</h2><p>Credits, usage, remaining balance, and effective entitlement window.</p></div><StatusBadge label={`${leaveEmployees.length} employees`} /></header><div className="hr-panel-body"><div className="hr-balance-list">{leaveEmployees.map((employee) => <div className="hr-balance-row" key={employee.id}><div><strong>{employee.full_name}</strong><small>{employee.employee_code || "—"} · {employee.department || "Unassigned"}</small></div><div>{employee.balances.length ? employee.balances.map((balance) => <div key={balance.leave_type_id}><strong>{balance.leave_type_name}: {num(balance.remaining)} left</strong><small>{num(balance.used)} used of {num(balance.credits)} · {entitlementWindow(balance)}</small></div>) : <span className="muted">No entitlement set</span>}</div></div>)}{!leaveEmployees.length ? <div className="people-empty">No leave balance records found.</div> : null}</div></div></section>
      </div>

      <div className="hr-stack">
        {canCreate ? <section className="hr-panel"><header><div><h2>Add HR record</h2><p>Memo, infraction, recognition, or annual review.</p></div></header><div className="hr-panel-body"><HrRecordForm employees={employees} /></div></section> : null}
        {canManageEntitlements ? <section className="hr-panel"><header><div><h2>Set leave entitlement</h2><p>Credits, eligibility, and effective dates.</p></div></header><div className="hr-panel-body"><LeaveEntitlementForm employees={employees} leaveTypes={leaveTypes} defaultYear={leaveBalanceResponse.year} /></div></section> : null}
      </div>
    </div>

    <SectionCard><SectionHeader title="HR record timeline" description="Formal employee records remain available as an auditable history." actions={<StatusBadge label={`${records.length} records`} />} /><SectionBody flush><div className="people-table-wrap"><table className="hr-record-table"><thead><tr><th>Date</th><th>Employee</th><th>Type</th><th>Subject</th><th>Severity</th><th>Status</th><th>Issued by</th></tr></thead><tbody>{records.map((record) => <tr key={record.id}><td>{record.record_date}</td><td><strong>{record.employee_name}</strong><br /><span className="muted">{record.department || "—"} · {record.position || "—"}</span></td><td>{record.record_type}</td><td>{record.subject}{record.rating != null ? ` · Rating ${record.rating}` : ""}</td><td>{record.severity}</td><td><StatusBadge label={record.status} tone={["Closed", "Resolved", "Finalized"].includes(record.status) ? "ok" : "warning"} /></td><td>{record.issued_by || "—"}</td></tr>)}{!records.length ? <tr><td colSpan={7}>No HR records yet.</td></tr> : null}</tbody></table></div></SectionBody></SectionCard>
  </div></Shell>;
}
