import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRuns, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";

function statusTone(status: string): "ok" | "warning" | "danger" {
  if (status === "Approved" || status === "Paid" || status === "Released") return "ok";
  if (status === "Draft" || status === "For Owner Review") return "warning";
  return "danger";
}

export default async function PayrollRunsPage({ searchParams }: { searchParams: Promise<{ status?: string; start?: string; end?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;

  const filters = await searchParams;
  const runs = await getPayrollRuns();
  const filtered = runs.filter((run) => (!filters.status || run.status === filters.status) && (!filters.start || run.period_start === filters.start) && (!filters.end || run.period_end === filters.end));
  const draftCount = runs.filter((run) => run.status === "Draft").length;
  const reviewCount = runs.filter((run) => run.status === "For Owner Review").length;
  const approvedCount = runs.filter((run) => run.status === "Approved").length;
  const paidCount = runs.filter((run) => run.status === "Paid" || run.status === "Released").length;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page run-page">
        <header className="payroll-hero"><div><span className="eyebrow">Payroll lifecycle</span><h1>Payroll runs</h1><p className="muted">Track each cutoff from draft through owner review, approval, payment, payslips, reports, corrections, and audit history.</p></div><div className="payroll-actions"><Link className="button secondary" href="/payroll">Preview payroll</Link><Link className="button" href="/cutoff">Open cutoff control</Link></div></header>

        <section className="run-kpis"><div className="run-kpi"><strong>{draftCount}</strong><span>Draft</span></div><div className="run-kpi"><strong>{reviewCount}</strong><span>For owner review</span></div><div className="run-kpi"><strong>{approvedCount}</strong><span>Approved</span></div><div className="run-kpi"><strong>{paidCount}</strong><span>Paid or released</span></div></section>

        <section className="payroll-toolbar"><form className="run-filter"><label>Status<select name="status" defaultValue={filters.status || ""}><option value="">All statuses</option><option>Draft</option><option>For Owner Review</option><option>Approved</option><option>Paid</option></select></label><label>Period start<input name="start" type="date" defaultValue={filters.start || ""} /></label><label>Period end<input name="end" type="date" defaultValue={filters.end || ""} /></label><button className="button" type="submit">Apply filters</button><Link className="button ghost" href="/payroll/runs">Reset</Link></form></section>

        <section className="run-list"><header><div><h2>Saved payroll runs</h2><p>{filtered.length} of {runs.length} records shown. Paid runs remain available as immutable history.</p></div><StatusBadge label={`${runs.length} total`} /></header><div className="table-wrap"><table className="run-table"><thead><tr><th>Run</th><th>Period</th><th>Status</th><th>Prepared / approved</th><th>Employees</th><th>Net payroll</th><th>Workspace</th></tr></thead><tbody>{filtered.map((run) => <tr key={run.id}><td><strong>#{run.id}</strong></td><td><span className="run-period"><strong>{run.period_start} to {run.period_end}</strong><small>{run.run_label || "Regular payroll"}</small></span></td><td><StatusBadge label={run.status} tone={statusTone(run.status)} /></td><td><strong>{run.prepared_by || "—"}</strong><br /><span className="muted">Approved: {run.approved_by || "—"}</span></td><td>{run.totals?.employees ?? 0}</td><td><strong>{peso(run.totals?.net_pay)}</strong></td><td><div className="run-actions"><Link className="button small" href={`/payroll/runs/${run.id}`}>Open run</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/payslips`}>Payslips</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/reports`}>Reports</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/corrections`}>Corrections</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/audit`}>Audit</Link></div></td></tr>)}{filtered.length === 0 ? <tr><td colSpan={7}>No payroll runs match the selected filters.</td></tr> : null}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
