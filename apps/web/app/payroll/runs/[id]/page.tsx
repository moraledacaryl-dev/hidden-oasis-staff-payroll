import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { MarkPaidButton } from "@/components/MarkPaidButton";
import { PayrollRevisionBanner } from "@/components/PayrollRevisionBanner";
import { getPayrollRunChangeDelta, getPayrollRunReview, numberText, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";

function warningSummary(value?: string | null): string {
  const count = String(value || "").split("\n").map((line) => line.trim()).filter(Boolean).length;
  return count ? `${count} warning${count === 1 ? "" : "s"}` : "—";
}

function statusTone(status: string): "ok" | "warning" | "danger" {
  if (status === "Approved" || status === "Paid" || status === "Released") return "ok";
  if (status === "Draft" || status === "For Owner Review") return "warning";
  return "danger";
}

export default async function PayrollRunReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const { id } = await params;
  const runId = Number(id);
  const [review, delta] = await Promise.all([
    getPayrollRunReview(runId),
    getPayrollRunChangeDelta(runId).catch(() => ({ ok: true, run_id: runId, changed: false, change_count: 0, changes: [] })),
  ]);
  const run = review.run;
  const items = review.items;
  const warningCount = items.filter((item) => item.warnings && item.warnings.trim().length > 0).length;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payroll Review</span><h1>Run #{run.id} · {run.period_start} to {run.period_end}</h1><p className="muted">Review payroll detail. Saved runs are snapshots; later schedule or actual edits do not change this run unless you save a revised payroll run.</p><div className="action-row"><Link className="button ghost" href={`/payroll/runs/${run.id}/reports`}>Reports</Link><Link className="button ghost" href={`/payroll/runs/${run.id}/audit`}>Audit timeline</Link><Link className="button ghost" href={`/payroll/runs/${run.id}/corrections`}>Corrections</Link><Link className="button ghost" href={`/payroll/runs/${run.id}/payslips`}>Payslips</Link>{session?.role_key === "owner" && run.status === "Approved" && !run.paid_at ? <MarkPaidButton runId={run.id} /> : null}</div></div><StatusBadge label={run.status} tone={statusTone(run.status)} /></header>
        <PayrollRevisionBanner runId={run.id} delta={delta} />
        <section className="grid cols-4"><div className="card"><strong>Employees</strong><p>{run.totals?.employees ?? items.length}</p></div><div className="card"><strong>Gross pay</strong><p>{peso(run.totals?.gross_pay)}</p></div><div className="card"><strong>Deductions</strong><p>{peso(run.totals?.total_deductions)}</p></div><div className="card"><strong>Net pay</strong><p>{peso(run.totals?.net_pay)}</p></div></section>
        <section className="grid cols-3"><div className="card"><strong>Prepared by</strong><p>{run.prepared_by || "—"}</p></div><div className="card"><strong>Approved by</strong><p>{run.approved_by || "—"}</p></div><div className="card"><strong>Employees with warnings</strong><p>{warningCount}</p></div></section>
        <section className="card"><div className="panel-title"><div><h2>Payroll items</h2><p className="muted">Employee-level payroll values stored in this run. These values do not silently change after schedule/actual edits.</p></div></div><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Dept</th><th>Reg hrs</th><th>OT hrs</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Warnings</th></tr></thead><tbody>{items.map((item) => (<tr key={item.id}><td>{item.employee_name}</td><td>{item.department}</td><td>{numberText(item.regular_hours)}</td><td>{numberText(item.approved_ot_hours)}</td><td>{peso(item.gross_pay)}</td><td>{peso(item.total_deductions)}</td><td>{peso(item.net_pay)}</td><td>{warningSummary(item.warnings)}</td></tr>))}{items.length === 0 ? <tr><td colSpan={8}>No payroll items found.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><h2>Payslip basis</h2><p className="muted">This is the payslip basis saved in this payroll run.</p><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Regular</th><th>OT</th><th>Night diff</th><th>Holiday</th><th>Cash advance</th><th>Gov/tax</th><th>Net</th></tr></thead><tbody>{items.map((item) => (<tr key={`slip-${item.id}`}><td>{item.employee_name}</td><td>{peso(item.regular_pay)}</td><td>{peso(item.ot_pay)}</td><td>{peso(item.night_diff_pay)}</td><td>{peso(item.holiday_pay)}</td><td>{peso(item.cash_advance_deduction)}</td><td>{peso((item.sss_ee || 0) + (item.philhealth_ee || 0) + (item.pagibig_ee || 0) + (item.tax || 0))}</td><td>{peso(item.net_pay)}</td></tr>))}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
