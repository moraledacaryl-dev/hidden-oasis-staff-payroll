import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";
import { numberText, peso } from "@/lib/api";
import "./print.css";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function apiHeaders(json = false): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

type SlipRun = { id: number; period_start: string; period_end: string; payout_date: string; run_label: string; status: string; employee_count: number; distributed_count: number; totals?: { net_pay: number } };
type SlipItem = { id: number; employee_id: number; employee_name: string; employee_code?: string; department: string; regular_hours: number; approved_ot_hours: number; gross_pay: number; total_deductions: number; net_pay: number; sss_ee: number; philhealth_ee: number; pagibig_ee: number; tax: number; cash_advance_deduction: number; other_deductions: number; distribution?: { distributed: boolean; distributed_at?: string | null; distributed_by?: string | null; method?: string | null } };
type SlipDetail = { ok: boolean; run: SlipRun; items: SlipItem[] };

async function loadRuns(): Promise<SlipRun[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/payslips/runs`, { headers: await apiHeaders(), cache: "no-store" });
  if (!response.ok) return [];
  return response.json();
}

async function loadDetail(runId: number): Promise<SlipDetail | null> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/payslips/runs/${runId}`, { headers: await apiHeaders(), cache: "no-store" });
  if (!response.ok) return null;
  return response.json();
}

async function markDistributed(formData: FormData) {
  "use server";
  const runId = Number(formData.get("run_id"));
  const employeeId = Number(formData.get("employee_id"));
  if (!runId || !employeeId) return;
  await fetch(`${apiBaseUrl()}/api/v1/payslips/runs/${runId}/employees/${employeeId}/distributed`, {
    method: "POST",
    headers: await apiHeaders(true),
    body: JSON.stringify({ method: "Printed" }),
    cache: "no-store",
  });
  revalidatePath("/payslips");
}

function PayslipCopy({ item, run, copyLabel, companyCopy = false }: { item: SlipItem; run: SlipRun; copyLabel: string; companyCopy?: boolean }) {
  const mandatory = Number(item.sss_ee || 0) + Number(item.philhealth_ee || 0) + Number(item.pagibig_ee || 0);
  const other = Number(item.tax || 0) + Number(item.cash_advance_deduction || 0) + Number(item.other_deductions || 0);

  return (
    <div className={`payslip-copy${companyCopy ? " company-copy" : ""}`}>
      <div className="copy-label">{copyLabel}</div>
      <div className="payslip-top">
        <div>
          <span className="eyebrow">Hidden Oasis</span>
          <h2>Employee Payslip</h2>
          <div className="payslip-meta">
            <p className="muted">Period: {run.period_start} to {run.period_end}</p>
            <p className="muted">Run #{run.id}</p>
          </div>
        </div>
        <div className="payslip-net"><span>Net Pay</span><strong>{peso(item.net_pay)}</strong></div>
      </div>
      <div className="payslip-employee"><h3>{item.employee_name}</h3><p className="muted">Department: {item.department}</p></div>
      <div className="payslip-summary">
        <div><span>Regular</span><strong>{numberText(item.regular_hours)} hrs</strong></div>
        <div><span>OT</span><strong>{numberText(item.approved_ot_hours)} hrs</strong></div>
        <div><span>Gross</span><strong>{peso(item.gross_pay)}</strong></div>
      </div>
      <div className="payslip-columns">
        <section><h3>Earnings</h3><p><span>Gross pay</span><strong>{peso(item.gross_pay)}</strong></p></section>
        <section>
          <h3>Deductions</h3>
          <p><span>Mandatory</span><strong>{peso(mandatory)}</strong></p>
          <p><span>Tax / advances / other</span><strong>{peso(other)}</strong></p>
          <p className="total-line"><span>Total deductions</span><strong>{peso(item.total_deductions)}</strong></p>
        </section>
      </div>
      <div className="payslip-signature"><span>Received by: __________________________</span><span>Date: _______________</span></div>
    </div>
  );
}

export default async function PayslipDistributionPage({ searchParams }: { searchParams: Promise<{ run_id?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }
  const params = await searchParams;
  const runs = await loadRuns();
  const selectedRunId = Number(params.run_id || runs[0]?.id || 0);
  const detail = selectedRunId ? await loadDetail(selectedRunId) : null;
  const run = detail?.run;
  const items = detail?.items || [];
  const pending = items.filter((item) => !item.distribution?.distributed).length;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page payslip-page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Payslip Distribution</span><h1>Approved payslips</h1><p className="muted">View, print, and record distribution.</p></div>
          <StatusBadge label={pending ? `${pending} pending` : "complete"} tone={pending ? "warning" : "ok"} />
        </header>
        <section className="card">
          <div className="panel-title"><div><h2>Payroll period</h2><p className="muted">Only approved or paid runs are listed.</p></div>{items.length ? <PrintButton label="Print payslips" /> : null}</div>
          <div className="action-row">{runs.map((item) => <a className={item.id === selectedRunId ? "button" : "button ghost"} href={`/payslips?run_id=${item.id}`} key={item.id}>#{item.id} · {item.period_start} to {item.period_end}</a>)}</div>
        </section>
        {run ? <section className="grid cols-3"><div className="card"><strong>{items.length}</strong><p className="muted">Payslips</p></div><div className="card"><strong>{items.length - pending}</strong><p className="muted">Distributed</p></div><div className="card"><strong>{peso(run.totals?.net_pay)}</strong><p className="muted">Net payroll</p></div></section> : null}
        <section className="card">
          <div className="panel-title"><div><h2>Distribution list</h2><p className="muted">Mark each payslip after handoff.</p></div></div>
          <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Department</th><th>Net pay</th><th>Status</th><th>Action</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.employee_name}</strong><br /><span className="muted">{item.employee_code || "—"}</span></td><td>{item.department || "—"}</td><td>{peso(item.net_pay)}</td><td>{item.distribution?.distributed ? `Distributed · ${item.distribution.distributed_at || ""}` : "Pending"}</td><td>{item.distribution?.distributed ? <span className="muted">{item.distribution.distributed_by || "Recorded"}</span> : <form action={markDistributed}><input type="hidden" name="run_id" value={selectedRunId} /><input type="hidden" name="employee_id" value={item.employee_id} /><button className="button small" type="submit">Mark distributed</button></form>}</td></tr>)}{items.length === 0 ? <tr><td colSpan={5}>No approved payslips available.</td></tr> : null}</tbody></table></div>
        </section>
        {run ? <section className="payslip-grid">{items.map((item) => <article className="payslip-sheet" key={`sheet-${item.id}`}><PayslipCopy item={item} run={run} copyLabel="Employee Copy" /><PayslipCopy item={item} run={run} copyLabel="Company Copy" companyCopy /></article>)}</section> : null}
      </div>
    </Shell>
  );
}
