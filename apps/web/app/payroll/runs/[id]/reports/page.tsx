import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRunReview, peso } from "@/lib/api";

function add(a: number | null | undefined, b: number | null | undefined) { return Number(a || 0) + Number(b || 0); }
function statusTone(status: string): "ok" | "warning" | "danger" { if (["Approved", "Paid", "Released"].includes(status)) return "ok"; if (["Draft", "For Owner Review"].includes(status)) return "warning"; return "danger"; }

type Group = { employees: number; gross: number; net: number; deductions: number };

export default async function PayrollRunReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const review = await getPayrollRunReview(Number(id));
  const run = review.run;
  const items = review.items;
  const departmentTotals = items.reduce<Record<string, Group>>((acc, item) => {
    const key = item.department || "Unassigned";
    acc[key] ||= { employees: 0, gross: 0, net: 0, deductions: 0 };
    acc[key].employees += 1;
    acc[key].gross += Number(item.gross_pay || 0);
    acc[key].net += Number(item.net_pay || 0);
    acc[key].deductions += Number(item.total_deductions || 0);
    return acc;
  }, {});
  const deductionTotals = items.reduce((acc, item) => {
    acc.sss += Number(item.sss_ee || 0);
    acc.philhealth += Number(item.philhealth_ee || 0);
    acc.pagibig += Number(item.pagibig_ee || 0);
    acc.tax += Number(item.tax || 0);
    acc.cashAdvance += Number(item.cash_advance_deduction || 0);
    acc.other += Number(item.other_deductions || 0);
    return acc;
  }, { sss: 0, philhealth: 0, pagibig: 0, tax: 0, cashAdvance: 0, other: 0 });
  const earningTotals = items.reduce((acc, item) => {
    acc.regular += Number(item.regular_pay || 0);
    acc.ot += Number(item.ot_pay || 0);
    acc.night += Number(item.night_diff_pay || 0);
    acc.holiday += Number(item.holiday_pay || 0);
    acc.leaveOther += add(item.paid_leave_pay, add(item.freelance_pay, item.other_earnings));
    return acc;
  }, { regular: 0, ot: 0, night: 0, holiday: 0, leaveOther: 0 });

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payroll Report</span><h1>Run #{run.id}</h1><p className="muted">Read-only summary for {run.period_start} to {run.period_end}.</p><div className="action-row"><Link className="button ghost" href={`/payroll/runs/${run.id}`}>Review</Link><Link className="button ghost" href={`/payroll/runs/${run.id}/audit`}>Audit</Link><Link className="button ghost" href={`/payroll/runs/${run.id}/payslips`}>Payslips</Link></div></div><StatusBadge label={run.status} tone={statusTone(run.status)} /></header>
        <section className="grid cols-4"><div className="card metric"><span className="eyebrow">Employees</span><strong className="metric-value">{run.totals?.employees ?? items.length}</strong></div><div className="card metric"><span className="eyebrow">Gross</span><strong className="metric-value">{peso(run.totals?.gross_pay)}</strong></div><div className="card metric"><span className="eyebrow">Deductions</span><strong className="metric-value">{peso(run.totals?.total_deductions)}</strong></div><div className="card metric"><span className="eyebrow">Net</span><strong className="metric-value">{peso(run.totals?.net_pay)}</strong></div></section>
        <section className="grid cols-2"><div className="card"><h2>Earnings Breakdown</h2><div className="table-wrap"><table><tbody><tr><td>Regular pay</td><td>{peso(earningTotals.regular)}</td></tr><tr><td>Overtime</td><td>{peso(earningTotals.ot)}</td></tr><tr><td>Night differential</td><td>{peso(earningTotals.night)}</td></tr><tr><td>Holiday</td><td>{peso(earningTotals.holiday)}</td></tr><tr><td>Leave / freelance / other</td><td>{peso(earningTotals.leaveOther)}</td></tr></tbody></table></div></div><div className="card"><h2>Deduction Breakdown</h2><div className="table-wrap"><table><tbody><tr><td>SSS</td><td>{peso(deductionTotals.sss)}</td></tr><tr><td>PhilHealth</td><td>{peso(deductionTotals.philhealth)}</td></tr><tr><td>Pag-IBIG</td><td>{peso(deductionTotals.pagibig)}</td></tr><tr><td>Withholding tax</td><td>{peso(deductionTotals.tax)}</td></tr><tr><td>Cash advance</td><td>{peso(deductionTotals.cashAdvance)}</td></tr><tr><td>Other deductions</td><td>{peso(deductionTotals.other)}</td></tr></tbody></table></div></div></section>
        <section className="card"><div className="panel-title"><div><h2>Department Totals</h2><p className="muted">Useful for management checking before export.</p></div></div><div className="table-wrap"><table><thead><tr><th>Department</th><th>Employees</th><th>Gross</th><th>Deductions</th><th>Net</th></tr></thead><tbody>{Object.entries(departmentTotals).map(([department, total]) => (<tr key={department}><td>{department}</td><td>{total.employees}</td><td>{peso(total.gross)}</td><td>{peso(total.deductions)}</td><td>{peso(total.net)}</td></tr>))}</tbody></table></div></section>
        <section className="card"><div className="panel-title"><div><h2>Employee Export Table</h2><p className="muted">Copy this table into sheets for now. CSV download can be added after deployment services are stable.</p></div></div><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Department</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Warnings</th></tr></thead><tbody>{items.map((item) => (<tr key={item.id}><td>{item.employee_name}</td><td>{item.department}</td><td>{peso(item.gross_pay)}</td><td>{peso(item.total_deductions)}</td><td>{peso(item.net_pay)}</td><td>{item.warnings ? "Has warning" : "—"}</td></tr>))}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
