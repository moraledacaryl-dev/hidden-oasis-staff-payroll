import Link from "next/link";
import { redirect } from "next/navigation";
import { CashAdvanceForm } from "@/components/CashAdvanceForm";
import { CashAdvanceCreditSettlementForm } from "@/components/CashAdvanceCreditSettlementForm";
import { ManualRepaymentForm } from "@/components/ManualRepaymentForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { PageHeading } from "@/components/UiPrimitives";
import { apiBaseUrl, backendHeaders, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";
import "./cash-advances.css";

type Employee = { id: number; full_name: string };
type Repayment = { id: number; repayment_date: string; amount: number; source: string; payment_method?: string | null; period_start?: string | null; period_end?: string | null; created_by?: string | null };
type Advance = { id: number; employee_id: number; full_name?: string; employee_code?: string; department?: string; advance_date: string; amount: number; deduction_per_payroll: number; remaining_balance: number; total_repaid?: number; overpayment_credit?: number; repayment_method?: string; status: string; reason?: string | null; repayments?: Repayment[] };
const activeStatuses = new Set(["Active", "Approved", "Partially Paid", "Released"]);
async function loadAdvances(): Promise<Advance[]> { const response = await fetch(`${apiBaseUrl()}/api/v1/cash-advances`, { headers: await backendHeaders(), cache: "no-store" }); if (!response.ok) throw new Error(`Cash advances could not be loaded (${response.status}).`); const data = await response.json().catch(() => ({})); return data.items || []; }
async function loadEmployees(): Promise<Employee[]> { const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/employees`, { headers: await backendHeaders(), cache: "no-store" }); if (!response.ok) throw new Error(`Employees could not be loaded (${response.status}).`); const data = await response.json().catch(() => ({})); return data.items || []; }
function formatDate(value: string): string { if (!value) return "—"; const date = new Date(`${value.slice(0, 10)}T00:00:00`); return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("en-PH", { month: "short", day: "numeric", year: "numeric" }); }
function statusLabel(status: string): string { return status === "Approved" || status === "Released" ? "Active" : status || "Active"; }

export default async function CashAdvancesPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  const canEditExisting = ["owner", "payroll"].includes(session.role_key);
  const isOwner = session.role_key === "owner";
  const loaded = await Promise.allSettled([loadAdvances(), loadEmployees()]);
  const failed = loaded.find((result) => result.status === "rejected");
  if (failed?.status === "rejected") return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page"><section className="card"><strong>Cash advances unavailable</strong><p className="muted">{failed.reason instanceof Error ? failed.reason.message : "Try again shortly."}</p></section></div></Shell>;
  const [advances, employees] = loaded.map((result) => result.status === "fulfilled" ? result.value : []) as [Advance[], Employee[]];
  const active = advances.filter((item) => activeStatuses.has(item.status) && Number(item.remaining_balance || 0) > 0);
  const totalBalance = active.reduce((sum, item) => sum + Number(item.remaining_balance || 0), 0);
  const totalRepaid = advances.reduce((sum, item) => sum + Number(item.total_repaid || 0), 0);
  const proposedDeduction = active.reduce((sum, item) => sum + Number(item.deduction_per_payroll || 0), 0);
  const creditToSettle = advances.reduce((sum, item) => sum + Number(item.overpayment_credit || 0), 0);

  return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page cash-advance-page people-page">
    <PageHeading eyebrow="People" title="Cash advances" description="Track active employee balances, proposed payroll deductions, repayments, and overpayment credits." actions={<Link className="button secondary" href="/staff">Staff directory</Link>} />
    <section className="cash-summary-grid"><div className="cash-summary-card"><span>Active advances</span><strong>{active.length}</strong></div><div className="cash-summary-card emphasis"><span>Outstanding</span><strong>{peso(totalBalance)}</strong></div><div className="cash-summary-card"><span>Proposed next deductions</span><strong>{peso(proposedDeduction)}</strong></div><div className="cash-summary-card"><span>Credits to settle</span><strong>{peso(creditToSettle)}</strong></div></section>
    <section><CashAdvanceForm employees={employees} isOwner={isOwner} /></section>
    <section className="cash-card-list">{advances.map((item) => { const original = Number(item.amount || 0); const balance = Number(item.remaining_balance || 0); const repaid = Number(item.total_repaid || 0); const credit = Number(item.overpayment_credit || 0); const paidPercent = original > 0 ? Math.min(100, Math.max(0, (repaid / original) * 100)) : 0; const isClosed = item.status === "Fully Paid" || item.status === "Cancelled"; return <article className={`cash-advance-card${isClosed ? " is-closed" : ""}`} key={item.id}><div className="cash-card-header"><div className="cash-card-person"><div className="cash-avatar" aria-hidden="true">{(item.full_name || "E").trim().charAt(0).toUpperCase()}</div><div><h2>{item.full_name || "Employee"}</h2><p>{item.employee_code || "No code"} · {item.department || "Unassigned"}</p></div></div><StatusBadge label={statusLabel(item.status)} tone={item.status === "Fully Paid" ? "ok" : item.status === "Cancelled" ? "danger" : "warning"} /></div><div className="cash-card-main"><div className="cash-balance-block"><span>Remaining balance</span><strong>{peso(balance)}</strong><small>of {peso(original)} issued</small></div><div className="cash-card-facts"><div><span>Repaid</span><strong>{peso(repaid)}</strong></div><div><span>Advance date</span><strong>{formatDate(item.advance_date)}</strong></div><div><span>Repayment</span><strong>{item.repayment_method || "Payroll deduction"}</strong></div></div></div><div className="cash-progress" aria-label={`${Math.round(paidPercent)}% repaid`}><div className="cash-progress-track"><span style={{ width: `${paidPercent}%` }} /></div><div className="cash-progress-label"><span>{Math.round(paidPercent)}% repaid</span><span>{balance <= 0 ? "Complete" : `${peso(balance)} left`}</span></div></div>{credit > 0 ? <div className="cash-reason"><span>Employee credit</span><p>{peso(credit)} was over-deducted and requires settlement.</p>{isOwner ? <CashAdvanceCreditSettlementForm advanceId={item.id} employeeId={item.employee_id} credit={credit} options={advances} /> : null}</div> : null}{item.reason ? <div className="cash-reason"><span>Reason</span><p>{item.reason}</p></div> : null}<div className="cash-card-footer"><div className="cash-primary-actions"><ManualRepaymentForm advanceId={item.id} balance={balance} employeeName={item.full_name || "employee"} />{canEditExisting ? <CashAdvanceForm employees={employees} item={item} canEditExisting isOwner={isOwner} /> : null}</div><details className="cash-history"><summary>Repayment history <span>{item.repayments?.length || 0}</span></summary><div className="cash-history-list">{(item.repayments || []).map((repayment) => <div className="cash-history-row" key={repayment.id}><div><strong>{peso(repayment.amount)}</strong><span>{repayment.source}</span></div><div><strong>{formatDate(repayment.repayment_date)}</strong><span>{repayment.source === "Payroll" ? `${repayment.period_start || ""}–${repayment.period_end || ""}` : repayment.payment_method || "—"}</span></div><div><span>Recorded by</span><strong>{repayment.created_by || "—"}</strong></div></div>)}{!item.repayments?.length ? <p className="cash-empty-history">No repayments recorded yet.</p> : null}</div></details></div></article>; })}{!advances.length ? <section className="card cash-empty-state"><h2>No cash advances</h2><p className="muted">No employee advance records have been created.</p></section> : null}</section>
    <section className="people-card"><h2>Portfolio position</h2><p>{peso(totalRepaid)} has been repaid across all recorded advances.</p></section>
  </div></Shell>;
}
