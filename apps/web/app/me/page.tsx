import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { StaffSelfServicePanel } from "@/components/StaffSelfServicePanel";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";
import { apiBaseUrl, numberText, peso } from "@/lib/api";

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
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return { ok: false, employee: null, items: [], message: "Not signed in." };
  const response = await fetch(`${apiBaseUrl()}/api/v1/me/payroll`, {
    headers: {
      Authorization: `Bearer ${token}`,
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
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

  return (
    <Shell allowedRoles={["staff"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">My Portal</span>
            <h1>Hi, {session.display_name}.</h1>
            <p className="muted">{payroll.ok && payroll.employee ? payroll.employee.department : "Staff self-service"}</p>
          </div>
          <StatusBadge label="staff" tone="warning" />
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>Linked employee</strong><p className="muted">{payroll.employee?.name || payroll.message || "Not linked"}</p></div>
          <div className="card"><strong>Payslips</strong><p className="muted">{payroll.items.length} visible</p></div>
          <div className="card"><strong>Password</strong><p className="muted">Use Settings → Password.</p></div>
        </section>

        <StaffSelfServicePanel />

        <section className="card">
          <div className="panel-title"><div><h2>My payslips</h2><p className="muted">Approved or paid payroll only. Open an individual payslip to print or save it as PDF.</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Period</th><th>Payout</th><th>Status</th><th>Hours</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Action</th></tr></thead>
              <tbody>
                {payroll.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.period_start} to {item.period_end}</td>
                    <td>{item.payout_date}</td>
                    <td>{item.status}</td>
                    <td>
                      <strong>{numberText(item.regular_hours)} regular hrs</strong>
                      {hasHours(item.approved_ot_hours) ? <><br /><span className="muted">{numberText(item.approved_ot_hours)} OT hrs</span></> : null}
                      {hasHours(item.night_diff_hours) ? <><br /><span className="muted">{numberText(item.night_diff_hours)} ND hrs</span></> : null}
                    </td>
                    <td>{peso(item.gross_pay)}</td>
                    <td>{peso(item.total_deductions)}</td>
                    <td><strong>{peso(item.net_pay)}</strong></td>
                    <td><Link className="primary-link" href={`/me/payslips/${item.id}`}>View / Download</Link></td>
                  </tr>
                ))}
                {!payroll.items.length ? <tr><td colSpan={8}>{payroll.message || "No payslips yet."}</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
