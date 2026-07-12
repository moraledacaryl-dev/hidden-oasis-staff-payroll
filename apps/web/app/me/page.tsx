import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { StaffSelfServicePanel } from "@/components/StaffSelfServicePanel";
import { currentSession } from "@/lib/session";
import { apiBaseUrl, backendHeaders, numberText, peso } from "@/lib/api";

type MyPayrollItem = {
  id: number;
  payroll_run_id: number;
  period_start: string;
  period_end: string;
  payout_date: string;
  run_label: string;
  status: string;
  regular_hours?: number | null;
  approved_ot_hours?: number | null;
  night_diff_hours?: number | null;
  gross_pay: number;
  total_deductions: number;
  net_pay: number;
};

type MyPayrollResponse = {
  ok: boolean;
  employee: { id: number; name: string; department: string } | null;
  items: MyPayrollItem[];
  message?: string;
};

function hasHours(value: number | null | undefined) {
  return Number(value || 0) > 0;
}

async function loadMyPayroll(): Promise<MyPayrollResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/me/payroll`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) return { ok: false, employee: null, items: [], message: data.detail || "No linked employee record." };
  return data as MyPayrollResponse;
}

export default async function MyPortalPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "staff") {
    return <Shell allowedRoles={["staff"]}><div /></Shell>;
  }
  const payroll = await loadMyPayroll();
  const latest = payroll.items[0];

  return (
    <Shell allowedRoles={["staff"]}>
      <div className="page staff-portal">
        <header className="staff-hero">
          <div>
            <span className="eyebrow">My workspace</span>
            <h1>Hi, {session.display_name}.</h1>
            <p className="muted">View your published schedule, requests, attendance, leave, payslips, and account settings in one place.</p>
          </div>
          <div className="staff-actions">
            <Link className="button ghost" href="/settings/password">Account</Link>
            <StatusBadge label={payroll.ok ? "employee linked" : "link required"} tone={payroll.ok ? "ok" : "warning"} />
          </div>
        </header>

        <section className="staff-summary">
          <div className="staff-summary-card"><span>Employee</span><strong>{payroll.employee?.name || "Not linked"}</strong><small>{payroll.employee?.department || payroll.message || "Contact an administrator"}</small></div>
          <div className="staff-summary-card"><span>Visible payslips</span><strong>{payroll.items.length}</strong><small>Approved or paid payroll only</small></div>
          <div className="staff-summary-card"><span>Latest net pay</span><strong>{latest ? peso(latest.net_pay) : "—"}</strong><small>{latest ? `${latest.period_start} to ${latest.period_end}` : "No payroll yet"}</small></div>
          <div className="staff-summary-card"><span>Latest hours</span><strong>{latest ? `${numberText(latest.regular_hours)}h` : "—"}</strong><small>{latest && hasHours(latest.approved_ot_hours) ? `${numberText(latest.approved_ot_hours)} OT hours` : "Regular hours"}</small></div>
        </section>

        <nav className="staff-quick-grid" aria-label="Staff portal sections">
          <a className="staff-quick-link" href="#my-schedule"><strong>My schedule</strong><span>Published shifts and change requests</span></a>
          <a className="staff-quick-link" href="#my-leave"><strong>Leave</strong><span>Balances, requests, and history</span></a>
          <a className="staff-quick-link" href="#my-attendance"><strong>Attendance</strong><span>Recorded time and decisions</span></a>
          <a className="staff-quick-link" href="#my-payslips"><strong>Payslips</strong><span>Approved and paid payroll</span></a>
        </nav>

        <StaffSelfServicePanel />

        <section className="staff-payslip-panel" id="my-payslips">
          <header><div><h2>My payslips</h2><p>Only approved or paid payroll is available here.</p></div><StatusBadge label={`${payroll.items.length} visible`} tone="ok" /></header>
          <div className="table-wrap">
            <table className="staff-payslip-table">
              <thead><tr><th>Period</th><th>Payout</th><th>Status</th><th>Hours</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Action</th></tr></thead>
              <tbody>
                {payroll.items.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.period_start} to {item.period_end}</strong><br /><span className="muted">{item.run_label || "Regular payroll"}</span></td>
                    <td>{item.payout_date}</td>
                    <td><StatusBadge label={item.status} tone="ok" /></td>
                    <td><strong>{numberText(item.regular_hours)} regular hrs</strong>{hasHours(item.approved_ot_hours) ? <><br /><span className="muted">{numberText(item.approved_ot_hours)} OT hrs</span></> : null}{hasHours(item.night_diff_hours) ? <><br /><span className="muted">{numberText(item.night_diff_hours)} ND hrs</span></> : null}</td>
                    <td>{peso(item.gross_pay)}</td>
                    <td>{peso(item.total_deductions)}</td>
                    <td><strong>{peso(item.net_pay)}</strong></td>
                    <td><Link className="button small" href={`/me/payslips/${item.id}`}>View payslip</Link></td>
                  </tr>
                ))}
                {!payroll.items.length ? <tr><td colSpan={8} className="staff-empty">{payroll.message || "No payslips yet."}</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
