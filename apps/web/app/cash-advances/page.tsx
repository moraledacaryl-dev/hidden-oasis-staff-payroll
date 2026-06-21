import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { CashAdvanceForm } from "@/components/CashAdvanceForm";
import { ManualRepaymentForm } from "@/components/ManualRepaymentForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, peso } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";
import "./cash-advances.css";

type Employee = { id: number; full_name: string };
type Repayment = { id: number; repayment_date: string; amount: number; source: string; payment_method?: string | null; period_start?: string | null; period_end?: string | null; created_by?: string | null };
type Advance = {
  id: number; employee_id: number; full_name?: string; employee_code?: string; department?: string;
  advance_date: string; amount: number; deduction_per_payroll: number; remaining_balance: number;
  total_repaid?: number; overpayment_credit?: number; repayment_method?: string; status: string; reason?: string | null; repayments?: Repayment[];
};

async function authHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}) };
}

async function loadAdvances(): Promise<Advance[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/cash-advances`, { headers: await authHeaders(), cache: "no-store" });
  if (!response.ok) return [];
  const data = await response.json().catch(() => ({}));
  return data.items || [];
}

async function loadEmployees(): Promise<Employee[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/employees`, { headers: await authHeaders(), cache: "no-store" });
  if (!response.ok) return [];
  const data = await response.json().catch(() => ({}));
  return data.items || [];
}

function formatDate(value: string): string {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("en-PH", { month: "short", day: "numeric", year: "numeric" });
}

export default async function CashAdvancesPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;

  const canEditExisting = ["owner", "payroll"].includes(session.role_key);
  const isOwner = session.role_key === "owner";
  const [advances, employees] = await Promise.all([loadAdvances(), loadEmployees()]);
  const active = advances.filter((item) => item.status === "Active");
  const totalBalance = active.reduce((sum, item) => sum + Number(item.remaining_balance || 0), 0);
  const totalRepaid = advances.reduce((sum, item) => sum + Number(item.total_repaid || 0), 0);

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page cash-advance-page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Cash Advances</span><h1>Employee advances</h1><p className="muted">Record advances, receive payments, and review outstanding balances.</p></div>
          <StatusBadge label={`${active.length} active`} tone={active.length ? "warning" : "ok"} />
        </header>

        <section className="cash-summary-grid">
          <div className="cash-summary-card"><span>Active advances</span><strong>{active.length}</strong></div>
          <div className="cash-summary-card emphasis"><span>Outstanding</span><strong>{peso(totalBalance)}</strong></div>
          <div className="cash-summary-card"><span>Total repaid</span><strong>{peso(totalRepaid)}</strong></div>
        </section>

        <section className="card cash-create-card">
          <div className="panel-title"><div><h2>Add cash advance</h2><p className="muted">Create a new advance and select how it will normally be repaid.</p></div></div>
          <CashAdvanceForm employees={employees} isOwner={isOwner} />
        </section>

        <section className="cash-card-list">
          {advances.map((item) => {
            const original = Number(item.amount || 0);
            const balance = Number(item.remaining_balance || 0);
            const repaid = Number(item.total_repaid || 0);
            const credit = Number(item.overpayment_credit || 0);
            const paidPercent = original > 0 ? Math.min(100, Math.max(0, (repaid / original) * 100)) : 0;
            const isClosed = item.status === "Fully Paid" || item.status === "Cancelled";

            return (
              <article className={`cash-advance-card${isClosed ? " is-closed" : ""}`} key={item.id}>
                <div className="cash-card-header">
                  <div className="cash-card-person">
                    <div className="cash-avatar" aria-hidden="true">{(item.full_name || "E").trim().charAt(0).toUpperCase()}</div>
                    <div><h2>{item.full_name || "Employee"}</h2><p>{item.employee_code || "No code"} · {item.department || "Unassigned"}</p></div>
                  </div>
                  <StatusBadge label={item.status} tone={item.status === "Fully Paid" ? "ok" : item.status === "Cancelled" ? "danger" : "warning"} />
                </div>

                <div className="cash-card-main">
                  <div className="cash-balance-block">
                    <span>Remaining balance</span>
                    <strong>{peso(balance)}</strong>
                    <small>of {peso(original)} issued</small>
                  </div>
                  <div className="cash-card-facts">
                    <div><span>Repaid</span><strong>{peso(repaid)}</strong></div>
                    <div><span>Advance date</span><strong>{formatDate(item.advance_date)}</strong></div>
                    <div><span>Repayment</span><strong>{item.repayment_method || "Payroll deduction"}</strong></div>
                  </div>
                </div>

                <div className="cash-progress" aria-label={`${Math.round(paidPercent)}% repaid`}>
                  <div className="cash-progress-track"><span style={{ width: `${paidPercent}%` }} /></div>
                  <div className="cash-progress-label"><span>{Math.round(paidPercent)}% repaid</span><span>{balance <= 0 ? "Complete" : `${peso(balance)} left`}</span></div>
                </div>

                {credit > 0 ? <div className="cash-reason"><span>Employee credit</span><p>{peso(credit)} was over-deducted and requires settlement.</p></div> : null}
                {item.reason ? <div className="cash-reason"><span>Reason</span><p>{item.reason}</p></div> : null}

                <div className="cash-card-footer">
                  <div className="cash-primary-actions">
                    <ManualRepaymentForm advanceId={item.id} balance={balance} employeeName={item.full_name || "employee"} />
                    {canEditExisting ? <CashAdvanceForm employees={employees} item={item} canEditExisting isOwner={isOwner} /> : null}
                  </div>
                  <details className="cash-history">
                    <summary>Repayment history <span>{item.repayments?.length || 0}</span></summary>
                    <div className="cash-history-list">
                      {(item.repayments || []).map((repayment) => (
                        <div className="cash-history-row" key={repayment.id}>
                          <div><strong>{peso(repayment.amount)}</strong><span>{repayment.source}</span></div>
                          <div><strong>{formatDate(repayment.repayment_date)}</strong><span>{repayment.source === "Payroll" ? `${repayment.period_start || ""}–${repayment.period_end || ""}` : repayment.payment_method || "—"}</span></div>
                          <div><span>Recorded by</span><strong>{repayment.created_by || "—"}</strong></div>
                        </div>
                      ))}
                      {!item.repayments?.length ? <p className="cash-empty-history">No repayments recorded yet.</p> : null}
                    </div>
                  </details>
                </div>
              </article>
            );
          })}
          {advances.length === 0 ? <section className="card cash-empty-state"><h2>No cash advances yet</h2><p className="muted">New advances will appear here with balance and repayment tracking.</p></section> : null}
        </section>
      </div>
    </Shell>
  );
}
