import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRuns, peso } from "@/lib/api";

function statusTone(status: string): "success" | "warning" | "danger" | "default" {
  if (status === "Approved") return "success";
  if (status === "Draft" || status === "For Owner Review") return "warning";
  if (status === "Paid" || status === "Released") return "success";
  return "default";
}

export default async function PayrollRunsPage({ searchParams }: { searchParams: Promise<{ status?: string; start?: string; end?: string }> }) {
  const filters = await searchParams;
  const runs = await getPayrollRuns();
  const filtered = runs.filter((run) => {
    if (filters.status && run.status !== filters.status) return false;
    if (filters.start && run.period_start !== filters.start) return false;
    if (filters.end && run.period_end !== filters.end) return false;
    return true;
  });

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Payroll Runs</span><h1>Run history</h1><p className="muted">Review, filter, audit, and open saved payroll runs. Release/pay remains disabled.</p></div></header>
        <section className="card"><form className="form-row"><div className="field"><label>Status</label><select name="status" defaultValue={filters.status || ""}><option value="">All</option><option value="Draft">Draft</option><option value="For Owner Review">For Owner Review</option><option value="Approved">Approved</option></select></div><div className="field"><label>Start</label><input name="start" type="date" defaultValue={filters.start || ""} /></div><div className="field"><label>End</label><input name="end" type="date" defaultValue={filters.end || ""} /></div><button className="primary-button" type="submit">Filter</button><Link className="button ghost" href="/payroll/runs">Reset</Link></form></section>
        <section className="card"><div className="panel-title"><div><h2>Saved runs</h2><p className="muted">{filtered.length} shown of {runs.length} total.</p></div></div><div className="table-wrap"><table><thead><tr><th>ID</th><th>Period</th><th>Status</th><th>Prepared</th><th>Approved</th><th>Employees</th><th>Net</th><th>Open</th></tr></thead><tbody>{filtered.map((run) => (<tr key={run.id}><td>{run.id}</td><td>{run.period_start} to {run.period_end}</td><td><StatusBadge label={run.status} tone={statusTone(run.status)} /></td><td>{run.prepared_by || "—"}</td><td>{run.approved_by || "—"}</td><td>{run.totals?.employees ?? 0}</td><td>{peso(run.totals?.net_pay)}</td><td><div className="action-row"><Link href={`/payroll/runs/${run.id}`}>Review</Link><Link href={`/payroll/runs/${run.id}/audit`}>Audit</Link></div></td></tr>))}{filtered.length === 0 ? <tr><td colSpan={8}>No payroll runs match the filters.</td></tr> : null}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
