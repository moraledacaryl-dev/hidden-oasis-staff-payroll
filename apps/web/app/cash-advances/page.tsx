import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { CashAdvanceForm } from "@/components/CashAdvanceForm";
import { ManualRepaymentForm } from "@/components/ManualRepaymentForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, peso } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

type Employee = { id: number; full_name: string };
type Repayment = { id: number; repayment_date: string; amount: number; source: string; payment_method?: string | null; period_start?: string | null; period_end?: string | null; created_by?: string | null };
type Advance = {
  id: number; employee_id: number; full_name?: string; employee_code?: string; department?: string;
  advance_date: string; amount: number; deduction_per_payroll: number; remaining_balance: number;
  total_repaid?: number; repayment_method?: string; status: string; reason?: string | null; repayments?: Repayment[];
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

export default async function CashAdvancesPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;

  const canEditExisting = ["owner", "payroll"].includes(session.role_key);
  const [advances, employees] = await Promise.all([loadAdvances(), loadEmployees()]);
  const active = advances.filter((item) => item.status === "Active");
  const totalBalance = active.reduce((sum, item) => sum + Number(item.remaining_balance || 0), 0);
  const totalRepaid = advances.reduce((sum, item) => sum + Number(item.total_repaid || 0), 0);

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Cash Advances</span><h1>Employee advances</h1><p className="muted">Record advances, receive partial payments, and keep every repayment traceable.</p></div>
          <StatusBadge label={`${active.length} active`} tone={active.length ? "warning" : "ok"} />
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>{active.length}</strong><p className="muted">Active advances</p></div>
          <div className="card"><strong>{peso(totalBalance)}</strong><p className="muted">Outstanding balance</p></div>
          <div className="card"><strong>{peso(totalRepaid)}</strong><p className="muted">Total repaid</p></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Add cash advance</h2><p className="muted">Choose payroll deduction for payroll-assisted repayment, or manual repayment when no automatic payroll deduction is intended.</p></div></div>
          <CashAdvanceForm employees={employees} />
        </section>

        <section className="grid">
          {advances.map((item) => (
            <article className="card" key={item.id}>
              <div className="panel-title">
                <div><h2>{item.full_name || "Employee"}</h2><p className="muted">{item.employee_code || "—"} · {item.department || "—"} · Advance dated {item.advance_date}</p></div>
                <StatusBadge label={item.status} tone={item.status === "Fully Paid" ? "ok" : item.status === "Cancelled" ? "danger" : "warning"} />
              </div>
              <div className="grid cols-4">
                <div><span className="muted">Original amount</span><strong>{peso(item.amount)}</strong></div>
                <div><span className="muted">Repaid</span><strong>{peso(item.total_repaid)}</strong></div>
                <div><span className="muted">Balance</span><strong>{peso(item.remaining_balance)}</strong></div>
                <div><span className="muted">Repayment setup</span><strong>{item.repayment_method || "Payroll deduction"}</strong></div>
              </div>
              <p className="muted">{item.reason || "No reason recorded."}</p>
              <div className="action-row">
                <ManualRepaymentForm advanceId={item.id} balance={Number(item.remaining_balance || 0)} employeeName={item.full_name || "employee"} />
                {canEditExisting ? <CashAdvanceForm employees={employees} item={item} canEditExisting /> : null}
              </div>
              <details>
                <summary>Repayment history ({item.repayments?.length || 0})</summary>
                <div className="table-wrap">
                  <table><thead><tr><th>Date</th><th>Source</th><th>Amount</th><th>Method / payroll</th><th>Recorded by</th></tr></thead><tbody>
                    {(item.repayments || []).map((repayment) => <tr key={repayment.id}><td>{repayment.repayment_date}</td><td>{repayment.source}</td><td>{peso(repayment.amount)}</td><td>{repayment.source === "Payroll" ? `${repayment.period_start || ""}–${repayment.period_end || ""}` : repayment.payment_method || "—"}</td><td>{repayment.created_by || "—"}</td></tr>)}
                    {!item.repayments?.length ? <tr><td colSpan={5}>No repayments recorded yet.</td></tr> : null}
                  </tbody></table>
                </div>
              </details>
            </article>
          ))}
          {advances.length === 0 ? <section className="card"><p>No cash advances recorded yet.</p></section> : null}
        </section>
      </div>
    </Shell>
  );
}
