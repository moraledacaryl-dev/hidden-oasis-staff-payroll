import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { PayrollCorrectionForm } from "@/components/PayrollCorrectionForm";
import { getEmployees, getPayrollCorrections, getPayrollRunReview, peso } from "@/lib/api";

function statusTone(status: string): "ok" | "warning" | "danger" {
  if (status === "Approved" || status === "Paid" || status === "Released") return "ok";
  if (status === "Draft" || status === "For Owner Review") return "warning";
  return "danger";
}

export default async function PayrollCorrectionsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runId = Number(id);
  const [review, corrections, employees] = await Promise.all([
    getPayrollRunReview(runId),
    getPayrollCorrections(runId),
    getEmployees(),
  ]);
  const run = review.run;

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payroll Corrections</span>
            <h1>Run #{run.id}</h1>
            <p className="muted">{run.period_start} to {run.period_end}. Corrections are recorded entries and do not silently rewrite paid payroll totals.</p>
            <div className="action-row">
              <Link className="button ghost" href={`/payroll/runs/${run.id}`}>Review run</Link>
              <Link className="button ghost" href={`/payroll/runs/${run.id}/audit`}>Audit timeline</Link>
            </div>
          </div>
          <StatusBadge label={run.status} tone={statusTone(run.status)} />
        </header>

        <section className="grid cols-4">
          <div className="card metric"><span className="eyebrow">Status</span><StatusBadge label={run.status} tone={statusTone(run.status)} /></div>
          <div className="card metric"><span className="eyebrow">Employees</span><strong className="metric-value">{run.totals?.employees ?? review.items.length}</strong></div>
          <div className="card metric"><span className="eyebrow">Net pay</span><strong className="metric-value">{peso(run.totals?.net_pay)}</strong></div>
          <div className="card metric"><span className="eyebrow">Corrections</span><strong className="metric-value">{corrections.items.length}</strong></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Add correction</h2><p className="muted">Use this for after-review notes or next-run earning/deduction adjustments.</p></div></div>
          <PayrollCorrectionForm runId={run.id} employees={employees} />
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Recorded corrections</h2><p className="muted">History is append-only from this page.</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Created</th><th>Employee</th><th>Type</th><th>Amount</th><th>Reason</th><th>Next run</th><th>By</th></tr></thead>
              <tbody>
                {corrections.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.created_at || "—"}</td>
                    <td>{item.employee_name || `Employee ${item.employee_id}`}</td>
                    <td>{item.adjustment_type}</td>
                    <td>{item.adjustment_type === "Note" ? "—" : peso(item.amount)}</td>
                    <td>{item.reason}</td>
                    <td>{item.apply_to_next_run ? "Yes" : "Record only"}</td>
                    <td>{item.created_by || "—"}</td>
                  </tr>
                ))}
                {!corrections.items.length ? <tr><td colSpan={7}>No corrections recorded for this run.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
