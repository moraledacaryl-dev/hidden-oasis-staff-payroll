import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { currentSession } from "@/lib/session";
import { numberText, peso } from "@/lib/api";
import "./print.css";

type SlipRun = { id: number; period_start: string; period_end: string; payout_date: string; run_label: string; status: string; employee_count: number; distributed_count: number; totals?: { net_pay: number } };
type SlipItem = { id: number; employee_id: number; employee_name: string; employee_code?: string; department: string; regular_hours: number; regular_pay?: number; approved_ot_hours: number; ot_pay?: number; night_diff_hours?: number; night_diff_pay?: number; holiday_pay?: number; paid_leave_days?: number; paid_leave_pay?: number; freelance_pay?: number; other_earnings?: number; gross_pay: number; total_deductions: number; net_pay: number; sss_ee: number; philhealth_ee: number; pagibig_ee: number; tax: number; cash_advance_deduction: number; other_deductions: number; leave_summary?: string[]; distribution?: { distributed: boolean; distributed_at?: string | null; distributed_by?: string | null; method?: string | null } };
type SlipDetail = { ok: boolean; run: SlipRun; items: SlipItem[] };

async function loadRuns(): Promise<SlipRun[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/payslips/runs`, { headers: await backendHeaders(), cache: "no-store" });
  if (!response.ok) throw new Error(`Payslip runs could not be loaded (${response.status}).`);
  return response.json();
}

async function loadDetail(runId: number): Promise<SlipDetail | null> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/payslips/runs/${runId}`, { headers: await backendHeaders(), cache: "no-store" });
  if (!response.ok) throw new Error(`Payslips could not be loaded (${response.status}).`);
  return response.json();
}

async function markDistributed(formData: FormData) {
  "use server";
  const runId = Number(formData.get("run_id"));
  const employeeId = Number(formData.get("employee_id"));
  if (!runId || !employeeId) return;
  const response = await fetch(`${apiBaseUrl()}/api/v1/payslips/runs/${runId}/employees/${employeeId}/distributed`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ method: "Printed" }),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Distribution update failed (${response.status}).`);
  revalidatePath("/payslips");
}

function hasValue(value: number | null | undefined) {
  return Number(value || 0) > 0;
}

function earningsTotal(item: SlipItem) {
  return Number(item.regular_pay || 0) + Number(item.ot_pay || 0) + Number(item.night_diff_pay || 0) + Number(item.holiday_pay || 0) + Number(item.paid_leave_pay || 0) + Number(item.freelance_pay || 0) + Number(item.other_earnings || 0);
}

function PayslipCopy({ item, run, copyLabel, companyCopy = false }: { item: SlipItem; run: SlipRun; copyLabel: string; companyCopy?: boolean }) {
  const mandatory = Number(item.sss_ee || 0) + Number(item.philhealth_ee || 0) + Number(item.pagibig_ee || 0);
  const other = Number(item.tax || 0) + Number(item.cash_advance_deduction || 0) + Number(item.other_deductions || 0);
  const regularPay = hasValue(item.regular_pay) ? Number(item.regular_pay) : Number(item.gross_pay || 0) - Number(item.ot_pay || 0) - Number(item.night_diff_pay || 0) - Number(item.holiday_pay || 0) - Number(item.paid_leave_pay || 0) - Number(item.freelance_pay || 0) - Number(item.other_earnings || 0);
  const showFallbackGross = Math.abs(earningsTotal(item) - Number(item.gross_pay || 0)) > 0.01;

  return (
    <div className={`payslip-copy${companyCopy ? " company-copy" : ""}`}>
      <div className="copy-label">{copyLabel}</div>
      <div className="payslip-top">
        <div>
          <span className="eyebrow">Hidden Oasis</span>
          <h2>Employee Payslip</h2>
          <div className="payslip-meta"><p className="muted">Period: {run.period_start} to {run.period_end}</p><p className="muted">Run #{run.id}</p></div>
        </div>
        <div className="payslip-net"><span>Net Pay</span><strong>{peso(item.net_pay)}</strong></div>
      </div>
      <div className="payslip-employee"><h3>{item.employee_name}</h3><p className="muted">Department: {item.department}</p></div>
      <div className="payslip-summary"><div><span>Regular</span><strong>{numberText(item.regular_hours)} hrs</strong></div><div><span>OT</span><strong>{numberText(item.approved_ot_hours)} hrs</strong></div><div><span>Gross</span><strong>{peso(item.gross_pay)}</strong></div></div>
      <div className="payslip-columns">
        <section>
          <h3>Earnings</h3>
          {hasValue(regularPay) ? <p><span>Regular pay</span><strong>{peso(regularPay)}</strong></p> : null}
          {hasValue(item.ot_pay) ? <p><span>Overtime pay</span><strong>{peso(item.ot_pay)}</strong></p> : null}
          {hasValue(item.night_diff_pay) ? <p><span>Night differential</span><strong>{peso(item.night_diff_pay)}</strong></p> : null}
          {hasValue(item.holiday_pay) ? <p><span>Holiday pay</span><strong>{peso(item.holiday_pay)}</strong></p> : null}
          {hasValue(item.paid_leave_pay) ? <p><span>Paid leave</span><strong>{peso(item.paid_leave_pay)}</strong></p> : null}
          {item.leave_summary?.length ? <div className="leave-lines"><strong>Leave details</strong>{item.leave_summary.map((line) => <span key={line}>{line}</span>)}</div> : null}
          {hasValue(item.freelance_pay) ? <p><span>Freelance / output pay</span><strong>{peso(item.freelance_pay)}</strong></p> : null}
          {hasValue(item.other_earnings) ? <p><span>Other earnings</span><strong>{peso(item.other_earnings)}</strong></p> : null}
          {showFallbackGross ? <p><span>Other gross pay</span><strong>{peso(Number(item.gross_pay || 0) - earningsTotal(item))}</strong></p> : null}
          <p className="total-line"><span>Gross pay</span><strong>{peso(item.gross_pay)}</strong></p>
        </section>
        <section>
          <h3>Deductions</h3>
          {hasValue(item.sss_ee) ? <p><span>SSS</span><strong>{peso(item.sss_ee)}</strong></p> : null}
          {hasValue(item.philhealth_ee) ? <p><span>PhilHealth</span><strong>{peso(item.philhealth_ee)}</strong></p> : null}
          {hasValue(item.pagibig_ee) ? <p><span>Pag-IBIG</span><strong>{peso(item.pagibig_ee)}</strong></p> : null}
          {hasValue(item.tax) ? <p><span>Withholding tax</span><strong>{peso(item.tax)}</strong></p> : null}
          {hasValue(item.cash_advance_deduction) ? <p><span>Cash advance</span><strong>{peso(item.cash_advance_deduction)}</strong></p> : null}
          {hasValue(item.other_deductions) ? <p><span>Other deductions</span><strong>{peso(item.other_deductions)}</strong></p> : null}
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
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  const params = await searchParams;
  let runs: SlipRun[];
  try { runs = await loadRuns(); } catch (error) { return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page"><section className="card"><strong>Payslips unavailable</strong><p className="muted">{error instanceof Error ? error.message : "Try again shortly."}</p></section></div></Shell>; }
  const selectedRunId = Number(params.run_id || runs[0]?.id || 0);
  let detail: SlipDetail | null = null;
  try { detail = selectedRunId ? await loadDetail(selectedRunId) : null; } catch (error) { return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page"><section className="card"><strong>Payslips unavailable</strong><p className="muted">{error instanceof Error ? error.message : "Try again shortly."}</p></section></div></Shell>; }
  const run = detail?.run;
  const items = detail?.items || [];
  const pending = items.filter((item) => !item.distribution?.distributed).length;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page payslip-page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payslip Distribution</span><h1>Approved payslips</h1></div><StatusBadge label={pending ? `${pending} pending` : "complete"} tone={pending ? "warning" : "ok"} /></header>
        <section className="card"><div className="panel-title"><h2>Payroll period</h2>{items.length ? <PrintButton label="Print payslips" /> : null}</div><div className="action-row">{runs.map((item) => <a className={item.id === selectedRunId ? "button" : "button ghost"} href={`/payslips?run_id=${item.id}`} key={item.id}>#{item.id} · {item.period_start} to {item.period_end}</a>)}</div></section>
        {run ? <section className="grid cols-3"><div className="card"><strong>{items.length}</strong><p className="muted">Payslips</p></div><div className="card"><strong>{items.length - pending}</strong><p className="muted">Distributed</p></div><div className="card"><strong>{peso(run.totals?.net_pay)}</strong><p className="muted">Net payroll</p></div></section> : null}
        <section className="card"><div className="panel-title"><h2>Distribution list</h2></div><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Department</th><th>Net pay</th><th>Status</th><th>Action</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.employee_name}</strong><br /><span className="muted">{item.employee_code || "—"}</span></td><td>{item.department || "—"}</td><td>{peso(item.net_pay)}</td><td>{item.distribution?.distributed ? `Distributed · ${item.distribution.distributed_at || ""}` : "Pending"}</td><td>{item.distribution?.distributed ? <span className="muted">{item.distribution.distributed_by || "Recorded"}</span> : <form action={markDistributed}><input type="hidden" name="run_id" value={selectedRunId} /><input type="hidden" name="employee_id" value={item.employee_id} /><button className="button small" type="submit">Mark distributed</button></form>}</td></tr>)}{items.length === 0 ? <tr><td colSpan={5}>No approved payslips available.</td></tr> : null}</tbody></table></div></section>
        {run ? <section className="payslip-grid">{items.map((item) => <article className="payslip-sheet" key={`sheet-${item.id}`}><PayslipCopy item={item} run={run} copyLabel="Employee Copy" /><div className="print-only-payslip-copy"><PayslipCopy item={item} run={run} copyLabel="Company Copy" companyCopy /></div></article>)}</section> : null}
      </div>
    </Shell>
  );
}
