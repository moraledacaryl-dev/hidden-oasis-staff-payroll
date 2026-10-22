import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRuns, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";

function statusTone(status: string): "ok" | "warning" | "danger" {
  if (status === "Approved" || status === "Paid" || status === "Released" || status === "Locked") return "ok";
  if (status === "Draft" || status === "For Owner Review") return "warning";
  return "danger";
}

export default async function PayrollRunsPage({ searchParams }: { searchParams: Promise<{ status?: string; start?: string; end?: string; view?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;

  const filters = await searchParams;
  const runs = await getPayrollRuns();
  const selectedView = filters.view === "superseded" || filters.view === "current" ? filters.view : "all";
  const filtered = runs.filter((run) =>
    (!filters.status || run.status === filters.status)
    && (!filters.start || run.period_start === filters.start)
    && (!filters.end || run.period_end === filters.end)
    && (selectedView === "all" || (selectedView === "superseded" ? Boolean(run.superseded_by_run_id) : !run.superseded_by_run_id))
  );
  const supersededCount = runs.filter((run) => Boolean(run.superseded_by_run_id)).length;
  const currentRuns = runs.filter((run) => !run.superseded_by_run_id);
  const draftCount = currentRuns.filter((run) => run.status === "Draft").length;
  const reviewCount = currentRuns.filter((run) => run.status === "For Owner Review" || run.status === "Reviewed").length;
  const approvedCount = currentRuns.filter((run) => run.status === "Approved").length;
  const paidCount = currentRuns.filter((run) => ["Paid", "Released", "Locked"].includes(run.status) || Boolean(run.paid_at)).length;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page run-page">
        <header className="payroll-hero"><div><span className="eyebrow">Payroll lifecycle</span><h1>Payroll runs</h1><p className="muted">Track each cutoff from draft through owner review, approval, payment, payslips, reports, corrections, and audit history.</p></div><div className="payroll-actions"><Link className="button secondary" href="/payroll">Preview payroll</Link><Link className="button" href="/cutoff">Open cutoff control</Link></div></header>

        <section className="run-kpis"><div className="run-kpi"><strong>{draftCount}</strong><span>Draft</span></div><div className="run-kpi"><strong>{reviewCount}</strong><span>For owner review</span></div><div className="run-kpi"><strong>{approvedCount}</strong><span>Approved</span></div><div className="run-kpi"><strong>{paidCount}</strong><span>Paid / locked / released</span></div><div className="run-kpi"><strong>{supersededCount}</strong><span>Superseded history</span></div></section>

        <section className="payroll-toolbar"><form className="run-filter"><label>Status<select name="status" defaultValue={filters.status || ""}><option value="">All statuses</option><option>Draft</option><option>For Owner Review</option><option>Approved</option><option>Paid</option><option>Locked</option><option>Released</option><option>Reviewed</option></select></label><label>Version<select name="view" defaultValue={selectedView}><option value="all">All versions</option><option value="current">Current only</option><option value="superseded">Superseded only</option></select></label><label>Period start<input name="start" type="date" defaultValue={filters.start || ""} /></label><label>Period end<input name="end" type="date" defaultValue={filters.end || ""} /></label><button className="button" type="submit">Apply filters</button><Link className="button ghost" href="/payroll/runs">Reset</Link></form></section>

        <section className="run-list"><header><div><h2>Recent payroll runs</h2><p>{filtered.length} of {runs.length} most recently returned records shown (up to 50). Superseded runs remain visible for audit only, not payment.</p></div><StatusBadge label={`${runs.length} total`} /></header><div className="table-wrap"><table className="run-table responsive-records"><thead><tr><th>Run</th><th>Period</th><th>Status</th><th>Prepared / approved</th><th>Employees</th><th>Net payroll</th><th>Workspace</th></tr></thead><tbody>{filtered.map((run) => <tr key={run.id}><td data-label="Run"><strong>#{run.id}</strong>{run.revision_of_run_id ? <small className="muted">Revision of #{run.revision_of_run_id}</small> : null}</td><td data-label="Period"><span className="run-period"><strong>{run.period_start} to {run.period_end}</strong><small>{run.run_label || "Regular payroll"}</small></span></td><td data-label="Status"><StatusBadge label={run.status} tone={statusTone(run.status)} />{run.superseded_by_run_id ? <small className="muted">Audit only · superseded by <Link href={`/payroll/runs/${run.superseded_by_run_id}`}>#{run.superseded_by_run_id}</Link></small> : null}</td><td data-label="Prepared / approved"><strong>{run.prepared_by || "—"}</strong><br /><span className="muted">Approved: {run.approved_by || "—"}</span></td><td data-label="Employees">{run.totals?.employees ?? 0}</td><td data-label="Net payroll"><strong>{peso(run.totals?.net_pay)}</strong></td><td data-label="Workspace"><div className="run-actions"><Link className="button small" href={`/payroll/runs/${run.id}`}>Open run</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/payslips`}>Payslips</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/reports`}>Reports</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/corrections`}>Corrections</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/audit`}>Audit</Link></div></td></tr>)}{filtered.length === 0 ? <tr><td colSpan={7}>No payroll runs match the selected filters.</td></tr> : null}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
