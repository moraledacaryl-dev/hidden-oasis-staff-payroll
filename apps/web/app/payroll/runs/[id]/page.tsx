import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { MarkPaidButton } from "@/components/MarkPaidButton";
import { PayrollWorkflowButton } from "@/components/PayrollWorkflowButton";
import { RecalculatePayrollButton } from "@/components/RecalculatePayrollButton";
import { PayrollRevisionBanner } from "@/components/PayrollRevisionBanner";
import { PayrollEmployeeAccordion } from "@/components/PayrollEmployeeAccordion";
import { PayrollReviewAccordion, ReviewAccordionDetails } from "@/components/PayrollReviewAccordion";
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
  const items = review.items;
  const editable = run.status === "Draft";
  const canRecalculate = editable && run.revision_treatment !== "adjust_paid";
  const warningCount = items.filter((item) => String(item.warnings || "").trim()).length;
  const versionText = run.revision_of_run_id ? `Revision of run #${run.revision_of_run_id}` : "Original payroll version";
  const audit = (review as unknown as {
    cash_advance_audit?: {
      expected_total?: number | null;
      applied_total?: number | null;
      issue_count?: number | null;
      rows?: Array<{
        employee_id?: number | null;
        name?: string | null;
        cash_advance_id?: number | null;
        advance_date?: string | null;
        expected?: number | null;
        applied?: number | null;
        balance_before_run?: number | null;
        balance_after_run?: number | null;
        status?: string | null;
        reason?: string | null;
      }> | null;
    };
  }).cash_advance_audit;
  const auditRows = Array.isArray(audit?.rows) ? audit.rows : [];
  const auditIssues = Number(audit?.issue_count || 0);
  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page"><PayrollReviewAccordion>
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

        {audit ? (
          <ReviewAccordionDetails id="cash-advance-panel" className="cash-advance-panel">
            <summary className="cash-advance-summary">
              <div className="cash-advance-header">
                <div>
                  <span className="cash-advance-eyebrow">Run-level deduction check</span>
                  <h2>Cash advances applied this payroll</h2>
                  <p>{auditRows.length} cash advances · {peso(audit.applied_total)} applied · {auditIssues} issue{auditIssues === 1 ? "" : "s"}</p>
                </div>
                <div className="cash-advance-summary-right">
                  <StatusBadge label={auditIssues ? "Needs Review" : "OK"} tone={auditIssues ? "danger" : "ok"} />
                  <span className="cash-advance-chevron">⌄</span>
                </div>
              </div>
            </summary>

            <div className="cash-advance-content">
              <p className="cash-advance-description">Payroll-deduction advances dated {run.period_start} to {run.period_end}. You do not need to open each employee to verify them.</p>

              <section className="cash-advance-stats">
              <div><span>Expected</span><strong>{peso(audit.expected_total)}</strong></div>
              <div><span>Applied</span><strong>{peso(audit.applied_total)}</strong></div>
              <div><span>Cash advances</span><strong>{auditRows.length}</strong></div>
              <div><span>Issues</span><strong>{auditIssues}</strong></div>
              </section>

              {auditRows.length ? (
              <div className="cash-advance-table-wrap">
                <table className="cash-advance-table">
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>Date</th>
                      <th>CA #</th>
                      <th className="amount">Balance</th>
                      <th className="amount">Expected</th>
                      <th className="amount">Applied</th>
                      <th className="amount">After</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditRows.map((row, index) => (
                      <tr key={`${row.employee_id || "employee"}-${row.cash_advance_id || index}`}>
                        <td>
                          <strong>{row.name || "Employee"}</strong>
                          {row.reason ? <small>{row.reason}</small> : null}
                        </td>
                        <td>{row.advance_date || "No date"}</td>
                        <td>#{row.cash_advance_id || "—"}</td>
                        <td className="amount">{peso(row.balance_before_run)}</td>
                        <td className="amount">{peso(row.expected)}</td>
                        <td className="amount">{peso(row.applied)}</td>
                        <td className="amount">{peso(row.balance_after_run)}</td>
                        <td>
                          <span className={`cash-advance-status cash-advance-status-${String(row.status || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
                            {row.status || "—"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              ) : (
                <p className="cash-advance-empty">No payroll-deduction cash advances dated inside this payroll period.</p>
              )}
            </div>
          </ReviewAccordionDetails>
        ) : null}

        <section>
          <div className="panel-title">
            <div><h2>Employees</h2><p className="muted">Open an employee to review earnings, deductions, final adjustments, and the read-only payslip preview.</p></div>
          </div>
          <div className="employee-payroll-list">
            <PayrollEmployeeAccordion runId={run.id} items={items} editable={editable} />
          </div>
        </section>
      </PayrollReviewAccordion></div>
    </Shell>
  );
}
