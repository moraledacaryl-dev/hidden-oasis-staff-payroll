import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { CashAdvanceForm } from "@/components/CashAdvanceForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl, peso } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

type Employee = { id: number; full_name: string };
type Advance = {
  id: number;
  employee_id: number;
  full_name?: string;
  employee_code?: string;
  department?: string;
  advance_date: string;
  amount: number;
  deduction_per_payroll: number;
  remaining_balance: number;
  status: string;
  reason?: string | null;
};

async function authHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
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

  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }

  const canEditExisting = ["owner", "payroll"].includes(session.role_key);
  const [advances, employees] = await Promise.all([loadAdvances(), loadEmployees()]);
  const active = advances.filter((item) => item.status === "Active");
  const totalBalance = active.reduce((sum, item) => sum + Number(item.remaining_balance || 0), 0);

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Cash Advances</span>
            <h1>Employee advances</h1>
            <p className="muted">{canEditExisting ? "Add old balances, correct mistakes, and track remaining balances." : "Input new cash advances. Existing records are owner/payroll locked."}</p>
          </div>
          <StatusBadge label={`${active.length} active`} tone={active.length ? "warning" : "ok"} />
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>{advances.length}</strong><p className="muted">Total records</p></div>
          <div className="card"><strong>{active.length}</strong><p className="muted">Active advances</p></div>
          <div className="card"><strong>{peso(totalBalance)}</strong><p className="muted">Remaining balance</p></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Add cash advance</h2><p className="muted">Supervisors can input new records. Only owner/payroll can correct existing records.</p></div></div>
          <CashAdvanceForm employees={employees} />
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Advance ledger</h2><p className="muted">Historical and active balances.</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Employee</th><th>Amount</th><th>Deduction</th><th>Balance</th><th>Status</th><th>Reason</th><th>Action</th></tr></thead>
              <tbody>
                {advances.map((item) => (
                  <tr key={item.id}>
                    <td>{item.advance_date}</td>
                    <td><strong>{item.full_name || "—"}</strong><br /><span className="muted">{item.employee_code || "—"} · {item.department || "—"}</span></td>
                    <td>{peso(item.amount)}</td>
                    <td>{peso(item.deduction_per_payroll)}</td>
                    <td>{peso(item.remaining_balance)}</td>
                    <td>{item.status}</td>
                    <td>{item.reason || "—"}</td>
                    <td><CashAdvanceForm employees={employees} item={item} canEditExisting={canEditExisting} /></td>
                  </tr>
                ))}
                {advances.length === 0 ? <tr><td colSpan={8}>No cash advances recorded yet.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
