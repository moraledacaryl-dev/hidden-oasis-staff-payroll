import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { MarkPaidButton } from "@/components/MarkPaidButton";
import { PayrollWorkflowButton } from "@/components/PayrollWorkflowButton";
import { RecalculatePayrollButton } from "@/components/RecalculatePayrollButton";
import { PayrollRevisionBanner } from "@/components/PayrollRevisionBanner";
import { EmployeePayrollCard } from "@/components/EmployeePayrollCard";
import { getPayrollRunChangeDelta, getPayrollRunReview, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";
import "./payroll-run.css";

function statusTone(status: string): "ok" | "warning" | "danger" {
  if (["Approved", "Paid", "Released"].includes(status)) return "ok";
  if (["Draft", "For Owner Review"].includes(status)) return "warning";
  return "danger";
}

export default async function PayrollRunReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  const { id } = await params;
  const runId = Number(id);
  const [review, delta] = await Promise.all([
    getPayrollRunReview(runId),
    getPayrollRunChangeDelta(runId).catch(() => ({ ok: true, run_id: runId, changed: false, change_count: 0, changes: [] })),
  ]);
  const run = review.run;
  const items = Array.isArray(review.items) ? review.items : [];
  const editable = run.status === "Draft";
  const canRecalculate = editable && run.revision_treatment !== "adjust_paid";
  const warningCount = items.filter((item) => String(item.warnings || "").trim()).length;
  const versionText = run.revision_of_run_id ? `Revision of run #${run.revision_of_run_id}` : "Original payroll version";
  const caAudit = review.cash_advance_audit;
  const caRows = Array.isArray(caAudit?.rows) ? caAudit.rows : [];
  const caIssues = caRows.filter((row) => row.status !== "OK");
  const caIssueCount = Number(caAudit?.issue_count || caIssues.length || 0);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payroll Review</span>
            <h1>Run #{run.id} · {run.period_start} to {run.period_end}</h1>
            <p className="muted">Review each employee&apos;s calculated pay, adjustments, deductions, and final payslip amount.</p>
            <div className="action-row">
              {canRecalculate ? <RecalculatePayrollButton runId={run.id} /> : null}
              {run.status === "Draft" ? <PayrollWorkflowButton runId={run.id} action="submit-review" /> : null}
              {session.role_key === "owner" && run.status === "For Owner Review" ? <PayrollWorkflowButton runId={run.id} action="approve" /> : null}
              <Link className="button ghost" href={`/payroll/runs/${run.id}/reports`}>Reports</Link>
              <Link className="button ghost" href={`/payroll/runs/${run.id}/audit`}>Audit timeline</Link>
              <Link className="button ghost" href={`/payroll/runs/${run.id}/corrections`}>Corrections</Link>
              <Link className="button ghost" href={`/payroll/runs/${run.id}/payslips`}>Payslips</Link>
              {session.role_key === "owner" && run.status === "Approved" && !run.paid_at ? <MarkPaidButton runId={run.id} /> : null}
            </div>
            {canRecalculate ? <p className="muted">Use Recalculate Draft after changing Schedule, Attendance, OT, Leave, employee payroll settings, or cash advances. Manual employee adjustments are preserved.</p> : null}
            {run.status === "Draft" ? <p className="muted">When all figures are correct, submit the run for owner review.</p> : null}
            {session.role_key === "owner" && run.status === "For Owner Review" ? <p className="muted">This run is ready for owner approval.</p> : null}
          </div>
          <StatusBadge label={run.status} tone={statusTone(run.status)} />
        </header>

        <div className="payroll-run-version-note">
          <strong>{versionText}.</strong> Only the latest approved version is the active payroll for this period. Older versions remain for audit and comparison.{run.revision_reason ? ` Revision reason: ${run.revision_reason}` : ""}
        </div>

        <PayrollRevisionBanner runId={run.id} delta={delta} runStatus={run.status} paidAt={run.paid_at} />

        <section className="grid cols-4">
          <div className="card"><strong>Employees</strong><p>{run.totals?.employees ?? items.length}</p></div>
          <div className="card"><strong>Gross pay</strong><p>{peso(run.totals?.gross_pay)}</p></div>
          <div className="card"><strong>Deductions</strong><p>{peso(run.totals?.total_deductions)}</p></div>
          <div className="card"><strong>Net payroll</strong><p>{peso(run.totals?.net_pay)}</p></div>
        </section>

        <section className="grid cols-3">
          <div className="card"><strong>Prepared by</strong><p>{run.prepared_by || "—"}</p></div>
          <div className="card"><strong>Approved by</strong><p>{run.approved_by || "—"}</p></div>
          <div className="card"><strong>Employees with warnings</strong><p>{warningCount}</p></div>
        </section>

        {caAudit ? (
          <section className="card">
            <div className="panel-title">
              <div>
                <h2>Cash advance deduction check</h2>
                <p className="muted">Only payroll-deduction cash advances dated inside {run.period_start} to {run.period_end} are expected by default.</p>
              </div>
              <StatusBadge label={String(caAudit.status || (caIssueCount ? "Needs Review" : "OK"))} tone={caIssueCount ? "danger" : "ok"} />
            </div>
            <section className="grid cols-4">
              <div className="card"><strong>Expected this period</strong><p>{peso(caAudit.expected_total)}</p></div>
              <div className="card"><strong>Applied in run</strong><p>{peso(caAudit.applied_total)}</p></div>
              <div className="card"><strong>Employees checked</strong><p>{caRows.length}</p></div>
              <div className="card"><strong>Issues</strong><p>{caIssueCount}</p></div>
            </section>
            {caIssues.length ? (
              <div className="action-list">
                {caIssues.map((row) => (
                  <div className="action-item" key={row.employee_id}>
                    <strong>{row.name}</strong>
                    <p className="muted">{row.period_advances} period advance(s) · {row.status}</p>
                    <p>Expected {peso(row.expected)} · Applied {peso(row.applied)}</p>
                  </div>
                ))}
              </div>
            ) : <p className="muted">All period cash advances match the payroll deduction amount.</p>}
          </section>
        ) : null}

        <section>
          <div className="panel-title">
            <div><h2>Employees</h2><p className="muted">Open an employee to review earnings, deductions, final adjustments, and the read-only payslip preview.</p></div>
          </div>
          <div className="employee-payroll-list">
            {items.map((item) => <EmployeePayrollCard key={item.id} runId={run.id} item={item} editable={editable} />)}
            {items.length === 0 ? <div className="card"><p>No payroll items found.</p></div> : null}
          </div>
        </section>
      </div>
    </Shell>
  );
}
