import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRunReview, numberText, peso } from "@/lib/api";

export default async function PayrollRunReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const review = await getPayrollRunReview(Number(id));
  const run = review.run;
  const items = review.items;
  const warningCount = items.filter((item) => item.warnings && item.warnings.trim().length > 0).length;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payroll Review</span><h1>Run #{run.id} · {run.period_start} to {run.period_end}</h1><p className="muted">Review-only payroll detail. This page does not release or mark payroll as paid.</p></div><StatusBadge label={run.status} tone={run.status === "Approved" ? "success" : run.status === "Draft" ? "warning" : "default"} /></header>
        <section className="grid cols-4"><div className="card"><strong>Employees</strong><p>{run.totals?.employees ?? items.length}</p></div><div className="card"><strong>Gross pay</strong><p>{peso(run.totals?.gross_pay)}</p></div><div className="card"><strong>Deductions</strong><p>{peso(run.totals?.total_deductions)}</p></div><div className="card"><strong>Net pay</strong><p>{peso(run.totals?.net_pay)}</p></div></section>
        <section className="grid cols-3"><div className="card"><strong>Prepared by</strong><p>{run.prepared_by || "—"}</p></div><div className="card"><strong>Approved by</strong><p>{run.approved_by || "—"}</p></div><div className="card"><strong>Warnings</strong><p>{warningCount}</p></div></section>
        <section className="card"><div className="panel-title"><div><h2>Payroll items</h2><p className="muted">Employee-level payroll preview stored in this run.</p></div></div><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Dept</th><th>Reg hrs</th><th>OT hrs</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Warnings</th></tr></thead><tbody>{items.map((item) => (<tr key={item.id}><td>{item.employee_name}</td><td>{item.department}</td><td>{numberText(item.regular_hours)}</td><td>{numberText(item.approved_ot_hours)}</td><td>{peso(item.gross_pay)}</td><td>{peso(item.total_deductions)}</td><td>{peso(item.net_pay)}</td><td>{item.warnings || "—"}</td></tr>))}{items.length === 0 ? <tr><td colSpan={8}>No payroll items found.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><h2>Payslip preview basis</h2><p className="muted">These fields are enough for the next step: printable payslip per employee. No payment action has been added yet.</p><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Regular</th><th>OT</th><th>Night diff</th><th>Holiday</th><th>Cash advance</th><th>Gov/tax</th><th>Net</th></tr></thead><tbody>{items.map((item) => (<tr key={`slip-${item.id}`}><td>{item.employee_name}</td><td>{peso(item.regular_pay)}</td><td>{peso(item.ot_pay)}</td><td>{peso(item.night_diff_pay)}</td><td>{peso(item.holiday_pay)}</td><td>{peso(item.cash_advance_deduction)}</td><td>{peso((item.sss_ee || 0) + (item.philhealth_ee || 0) + (item.pagibig_ee || 0) + (item.tax || 0))}</td><td>{peso(item.net_pay)}</td></tr>))}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
