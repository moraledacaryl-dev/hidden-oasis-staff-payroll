import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { getPayrollRunChangeDelta, getPayrollRunReview } from "@/lib/api";
import { currentSession } from "@/lib/session";

function shortJson(value: unknown) {
  if (!value) return "—";
  if (typeof value === "string") return value.length > 140 ? `${value.slice(0, 140)}…` : value;
  const text = JSON.stringify(value);
  return text.length > 140 ? `${text.slice(0, 140)}…` : text;
}

export default async function ScheduleChangesPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const { id } = await params;
  const runId = Number(id);
  const [review, rawDelta] = await Promise.all([getPayrollRunReview(runId), getPayrollRunChangeDelta(runId)]);
  const delta = rawDelta as typeof rawDelta & { baseline_run_id?: number | null; mode?: string };
  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div>
            <span className="eyebrow">Payroll Audit</span>
            <h1>Schedule changes · Run #{review.run.id}</h1>
            <p className="muted">Changes used to decide whether this payroll run needs revision or undo. Saved payroll items remain frozen.</p>
            <div className="action-row"><Link className="button ghost" href={`/payroll/runs/${runId}`}>Back to run</Link></div>
          </div>
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>Change count</strong><p>{delta.change_count}</p></div>
          <div className="card"><strong>Baseline run</strong><p>{delta.baseline_run_id || runId}</p></div>
          <div className="card"><strong>Mode</strong><p>{delta.mode || "—"}</p></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Change log</h2><p className="muted">Rows are ordered newest first.</p></div></div>
          <div className="table-wrap"><table>
            <thead><tr><th>ID</th><th>Date</th><th>Employee</th><th>Type</th><th>Entity</th><th>By</th><th>At</th><th>Undone</th></tr></thead>
            <tbody>
              {delta.changes.map((change) => {
                const detail = change as typeof change & { before_json?: string | null; after_json?: string | null };
                return (
                  <tr key={change.id} title={`Before: ${shortJson(detail.before_json)}\nAfter: ${shortJson(detail.after_json)}`}>
                    <td>{change.id}</td>
                    <td>{change.work_date || "—"}</td>
                    <td>{change.employee_id || "—"}</td>
                    <td>{change.change_type}</td>
                    <td>{change.entity_type} #{change.entity_id || "—"}</td>
                    <td>{change.changed_by || "—"}</td>
                    <td>{change.changed_at}</td>
                    <td>{change.undone_at || "No"}</td>
                  </tr>
                );
              })}
              {delta.changes.length === 0 ? <tr><td colSpan={8}>No schedule/actual changes found for this run window.</td></tr> : null}
            </tbody>
          </table></div>
        </section>
      </div>
    </Shell>
  );
}
