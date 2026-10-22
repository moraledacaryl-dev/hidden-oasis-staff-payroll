import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRunHistory, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";

function statusTone(status: string): "ok" | "warning" | "danger" {
  if (status === "Approved" || status === "Paid" || status === "Released" || status === "Locked") return "ok";
  if (status === "Draft" || status === "For Owner Review") return "warning";
  return "danger";
}

export default async function PayrollRunsPage({ searchParams }: { searchParams: Promise<{ status?: string; start?: string; end?: string; view?: string; page?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;

  const filters = await searchParams;
  const selectedView = filters.view === "superseded" || filters.view === "current" ? filters.view : "all";
  const page = Math.max(1, Math.min(100000, Number.parseInt(filters.page || "1", 10) || 1));
  const history = await getPayrollRunHistory({
    status: filters.status || undefined,
    start: filters.start || undefined,
    end: filters.end || undefined,
    view: selectedView,
    page,
    pageSize: 25,
  });
  const filtered = history.items;
  const { draft: draftCount, review: reviewCount, approved: approvedCount, paid: paidCount, superseded: supersededCount } = history.summary;
  const historyPageHref = (targetPage: number) => {
    const query = new URLSearchParams();
    if (filters.status) query.set("status", filters.status);
    if (filters.view && filters.view !== "all") query.set("view", filters.view);
    if (filters.start) query.set("start", filters.start);
    if (filters.end) query.set("end", filters.end);
    query.set("page", String(targetPage));
    return `/payroll/runs?${query.toString()}`;
  };
  const firstShown = history.total > 0 ? (history.page - 1) * history.page_size + 1 : 0;
  const lastShown = (history.page - 1) * history.page_size + filtered.length;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page run-page">
        <header className="payroll-hero"><div><span className="eyebrow">Payroll lifecycle</span><h1>Payroll runs</h1><p className="muted">Track each cutoff from draft through owner review, approval, payment, payslips, reports, corrections, and audit history.</p></div><div className="payroll-actions"><Link className="button secondary" href="/payroll">Preview payroll</Link><Link className="button" href="/cutoff">Open cutoff control</Link></div></header>

        <section className="run-kpis"><div className="run-kpi"><strong>{draftCount}</strong><span>Draft</span></div><div className="run-kpi"><strong>{reviewCount}</strong><span>For owner review</span></div><div className="run-kpi"><strong>{approvedCount}</strong><span>Approved</span></div><div className="run-kpi"><strong>{paidCount}</strong><span>Paid / locked / released</span></div><div className="run-kpi"><strong>{supersededCount}</strong><span>Superseded history</span></div></section>

        <section className="payroll-toolbar"><form className="run-filter"><label>Status<select name="status" defaultValue={filters.status || ""}><option value="">All statuses</option><option>Draft</option><option>For Owner Review</option><option>Approved</option><option>Paid</option><option>Locked</option><option>Released</option><option>Reviewed</option></select></label><label>Version<select name="view" defaultValue={selectedView}><option value="all">All versions</option><option value="current">Current only</option><option value="superseded">Superseded only</option></select></label><label>Period start<input name="start" type="date" defaultValue={filters.start || ""} /></label><label>Period end<input name="end" type="date" defaultValue={filters.end || ""} /></label><button className="button" type="submit">Apply filters</button><Link className="button ghost" href="/payroll/runs">Reset</Link></form></section>

        <section className="run-list"><header><div><h2>Payroll history</h2><p>{firstShown}–{lastShown} of {history.total} matching runs. Superseded runs remain audit-only, not payable. Summary counts above cover all saved versions.</p></div><StatusBadge label={`${history.total} match${history.total === 1 ? "" : "es"}`} /></header><div className="table-wrap"><table className="run-table responsive-records"><thead><tr><th>Run</th><th>Period</th><th>Status</th><th>Prepared / approved</th><th>Employees</th><th>Net payroll</th><th>Workspace</th></tr></thead><tbody>{filtered.map((run) => <tr key={run.id}><td data-label="Run"><strong>#{run.id}</strong>{run.revision_of_run_id ? <small className="muted">Revision of #{run.revision_of_run_id}</small> : null}</td><td data-label="Period"><span className="run-period"><strong>{run.period_start} to {run.period_end}</strong><small>{run.run_label || "Regular payroll"}</small></span></td><td data-label="Status"><StatusBadge label={run.status} tone={statusTone(run.status)} />{run.superseded_by_run_id ? <small className="muted">Audit only · superseded by <Link href={`/payroll/runs/${run.superseded_by_run_id}`}>#{run.superseded_by_run_id}</Link></small> : null}</td><td data-label="Prepared / approved"><strong>{run.prepared_by || "—"}</strong><br /><span className="muted">Approved: {run.approved_by || "—"}</span></td><td data-label="Employees">{run.totals?.employees ?? 0}</td><td data-label="Net payroll"><strong>{peso(run.totals?.net_pay)}</strong></td><td data-label="Workspace"><div className="run-actions"><Link className="button small" href={`/payroll/runs/${run.id}`}>Open run</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/payslips`}>Payslips</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/reports`}>Reports</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/corrections`}>Corrections</Link><Link className="button small ghost" href={`/payroll/runs/${run.id}/audit`}>Audit</Link></div></td></tr>)}{filtered.length === 0 ? <tr><td colSpan={7}>No payroll runs match the selected filters.</td></tr> : null}</tbody></table></div>
          <nav aria-label="Payroll history pages" className="report-actions" style={{ display: "flex", gap: "0.75rem", alignItems: "center", justifyContent: "flex-end", padding: "1rem" }}>
            {history.page > 1 ? <Link className="button small ghost" href={historyPageHref(history.page - 1)}>Previous page</Link> : null}
            <span className="muted">Page {history.page} of {Math.max(1, history.pages)}</span>
            {history.page < history.pages ? <Link className="button small ghost" href={historyPageHref(history.page + 1)}>Next page</Link> : null}
          </nav>
        </section>
      </div>
    </Shell>
  );
}
