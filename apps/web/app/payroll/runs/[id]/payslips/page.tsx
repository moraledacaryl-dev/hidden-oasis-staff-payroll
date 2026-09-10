import Link from "next/link";
import { redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { getPayrollRunReview } from "@/lib/api";
import { PayslipCopy } from "@/components/EmployeePayslip";
import { currentSession } from "@/lib/session";
import "./print.css";

export default async function PayslipPreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId) || runId <= 0) {
    return (
      <Shell allowedRoles={["owner", "payroll"]}>
        <div className="page"><section className="card"><h1>Invalid payroll run</h1><p className="muted">Open payslips from Payroll Runs instead.</p><Link className="primary-link" href="/payroll/runs">Back to payroll runs</Link></section></div>
      </Shell>
    );
  }

  let review;
  try {
    review = await getPayrollRunReview(runId);
  } catch {
    return (
      <Shell allowedRoles={["owner", "payroll"]}>
        <div className="page">
          <header className="page-header"><div className="grid"><span className="eyebrow">Payslips</span><h1>Run #{runId} unavailable</h1></div></header>
          <section className="card">
            <div className="action-row"><Link className="primary-link" href="/payroll/runs">Back to payroll runs</Link><Link className="primary-link" href="/payroll">Current payroll</Link></div>
          </section>
        </div>
      </Shell>
    );
  }

  const run = review.run;
  const items = review.items || [];

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page payslip-page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payslip Preview</span>
            <h1>Run #{run.id}</h1>
            <p className="muted">{run.period_start} to {run.period_end}. Employer contributions stay in payroll reports, not on employee payslips.</p>
             {run.superseded_by_run_id ? <p className="muted">This is an older payroll version superseded by Run #{run.superseded_by_run_id}. Use it for audit/history only; normal Payslip Distribution should use the latest active version.</p> : null}
             {run.revision_of_run_id ? <p className="muted">This is a revision of Run #{run.revision_of_run_id}. For already-paid payroll, distribute/pay only the adjustment difference unless this run is explicitly approved as the active corrected version.</p> : null}
            <div className="action-row"><Link className="primary-link" href="/payroll/runs">All runs</Link><Link className="primary-link" href={`/payroll/runs/${run.id}/reports`}>Report</Link><Link className="primary-link" href={`/payroll/runs/${run.id}/audit`}>Audit</Link></div>
          </div>
        </header>
        <section className="print-actions"><PrintButton label="Print payslips" /></section>
        {items.length === 0 ? <section className="card"><h2>No payroll items</h2><p className="muted">This run has no saved employee payroll lines yet.</p></section> : null}
        <section className="payslip-grid">
          {items.map((item) => (
            <article className="payslip-sheet" key={item.id}>
              <PayslipCopy item={item} run={run} copyLabel="Employee Copy" />
              <PayslipCopy item={item} run={run} copyLabel="Company Copy" companyCopy />
            </article>
          ))}
        </section>
      </div>
    </Shell>
  );
}
