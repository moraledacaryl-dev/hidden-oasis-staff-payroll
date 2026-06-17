import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollCorrections, getPayrollRunReview, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";
import styles from "./page.module.css";

function fmt(value?: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-PH", { dateStyle: "medium", timeStyle: "short" });
}

function statusTone(status: string): "ok" | "warning" | "danger" {
  if (status === "Approved" || status === "Paid" || status === "Released") return "ok";
  if (status === "Draft" || status === "For Owner Review") return "warning";
  return "danger";
}

export default async function PayrollRunAuditPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const { id } = await params;
  const [review, corrections] = await Promise.all([getPayrollRunReview(Number(id)), getPayrollCorrections(Number(id))]);
  const run = review.run;
  const totals = run.totals;
  const events = [
    { title: "Draft created", done: Boolean(run.created_at), detail: `Prepared by ${run.prepared_by || "Unknown"}`, time: fmt(run.created_at) },
    { title: "Locked for owner review", done: Boolean(run.locked_at), detail: "Locked for owner checking.", time: fmt(run.locked_at) },
    { title: "Owner approved", done: Boolean(run.approved_at), detail: `Approved by ${run.approved_by || "Not approved yet"}`, time: fmt(run.approved_at) },
    { title: "Returned to draft", done: Boolean(run.reopen_reason), detail: run.reopen_reason || "No return reason recorded.", time: run.reopen_reason ? "Reason recorded" : "Not returned" },
    { title: "Marked paid", done: Boolean(run.paid_at), detail: run.paid_at ? "Paid marker recorded." : "No paid marker yet.", time: fmt(run.paid_at) },
  ];

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payroll Audit</span>
            <h1>Run #{run.id}</h1>
            <p className="muted">Lifecycle timeline for {run.period_start} to {run.period_end}.</p>
          </div>
          <div className="action-row">
            <Link className="button ghost" href={`/payroll/runs/${run.id}`}>Review run</Link>
            <Link className="button ghost" href={`/payroll/runs/${run.id}/corrections`}>Corrections</Link>
            <Link className="button ghost" href={`/payroll/runs/${run.id}/payslips`}>Payslips</Link>
          </div>
        </header>

        <section className="grid cols-4">
          <div className="card metric"><span className="eyebrow">Status</span><StatusBadge label={run.status} tone={statusTone(run.status)} /></div>
          <div className="card metric"><span className="eyebrow">Employees</span><strong className="metric-value">{totals?.employees || review.items.length}</strong></div>
          <div className="card metric"><span className="eyebrow">Gross</span><strong className="metric-value">{peso(totals?.gross_pay)}</strong></div>
          <div className="card metric"><span className="eyebrow">Net</span><strong className="metric-value">{peso(totals?.net_pay)}</strong></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Lifecycle Timeline</h2><p className="muted">Audit view only.</p></div></div>
          <div className={styles.timeline}>
            {events.map((event) => (
              <article className={`${styles.item} ${event.done ? styles.done : ""}`} key={event.title}>
                <div className={styles.dot} />
                <div>
                  <div className="panel-title"><h3>{event.title}</h3><strong>{event.time}</strong></div>
                  <p className="muted">{event.detail}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="grid cols-2">
          <div className="card"><h2>Run Details</h2><div className={styles.facts}><p><span>Period</span><strong>{run.period_start} to {run.period_end}</strong></p><p><span>Payout date</span><strong>{run.payout_date}</strong></p><p><span>Run label</span><strong>{run.run_label}</strong></p><p><span>Validation</span><strong>{run.validation_summary || "No summary"}</strong></p></div></div>
          <div className="card"><h2>Status</h2><div className={styles.facts}><p><span>Approved</span><strong>{run.approved_at ? "Yes" : "No"}</strong></p><p><span>Paid</span><strong>{run.paid_at ? "Yes" : "No"}</strong></p><p><span>Paid marker</span><strong>{run.paid_at ? fmt(run.paid_at) : "Not recorded"}</strong></p></div></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Corrections</h2><p className="muted">Recorded, applied, or voided entries.</p></div></div>
          <div className="table-wrap"><table><thead><tr><th>Created</th><th>Employee</th><th>Type</th><th>Status</th><th>Amount</th><th>Reason</th></tr></thead><tbody>{corrections.items.map((item) => (<tr key={item.id}><td>{item.created_at || "—"}</td><td>{item.employee_name || `Employee ${item.employee_id}`}</td><td>{item.adjustment_type}</td><td>{item.status || "Recorded"}</td><td>{item.adjustment_type === "Note" ? "—" : peso(item.amount)}</td><td>{item.reason}</td></tr>))}{corrections.items.length === 0 ? <tr><td colSpan={6}>No corrections recorded.</td></tr> : null}</tbody></table></div>
        </section>
      </div>
    </Shell>
  );
}
