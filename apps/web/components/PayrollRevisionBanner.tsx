"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { PayrollRunChangeDelta } from "@/lib/api";

export function PayrollRevisionBanner({ runId, delta, runStatus, paidAt }: { runId: number; delta: PayrollRunChangeDelta; runStatus?: string | null; paidAt?: string | null }) {
  const router = useRouter();
  const status = String(runStatus || "").toLowerCase();
  const paid = Boolean(paidAt) || ["paid", "released"].includes(status);
  const draft = status === "draft";
  const [toolsOpen, setToolsOpen] = useState(Boolean(delta.changed));
  const [label, setLabel] = useState("");
  const [reason, setReason] = useState("");
  const [treatment, setTreatment] = useState<"replace_unpaid" | "adjust_paid">(paid ? "adjust_paid" : "replace_unpaid");
  const [confirmUndo, setConfirmUndo] = useState("");
  const [busy, setBusy] = useState<"revision" | "undo" | null>(null);
  const [message, setMessage] = useState("");

  if (draft) return null;

  async function saveRevision() {
    if (!reason.trim()) {
      setMessage("Enter the reason for this revision.");
      return;
    }
    setBusy("revision");
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/save-revision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_label: label || null, revision_reason: reason.trim(), treatment }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || data.message || "Could not save revised payroll run.");
      return;
    }
    const newId = data.run?.id;
    if (newId) router.push(`/payroll/runs/${newId}`);
    else router.refresh();
  }

  async function undoChanges() {
    setBusy("undo");
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/undo-schedule-changes`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || data.message || "Could not undo schedule/actual changes.");
      return;
    }
    setMessage(`Restored ${data.restored_changes || 0} change(s).`);
    router.refresh();
  }

  const visibleChanges = delta.changes.slice(0, 6);

  return (
    <section className={`card ${delta.changed ? "danger-card" : ""}`}>
      <button
        type="button"
        className="payroll-revision-toggle"
        aria-expanded={toolsOpen}
        onClick={() => setToolsOpen((open) => !open)}
      >
        <span>
          <span className="eyebrow">{delta.changed ? "Changes detected" : "Revision tools"}</span>
          <strong>{delta.changed ? `${delta.change_count} source change${delta.change_count === 1 ? "" : "s"} detected after save` : "Create a revision only when a saved payroll needs correction"}</strong>
        </span>
        <span aria-hidden="true">{toolsOpen ? "−" : "+"}</span>
      </button>

      {toolsOpen ? (
        <div className="payroll-revision-body">
          <div className="panel-title">
            <div>
              <h2>{delta.changed ? "Source records changed after this payroll was saved" : "Create a revision for this past payroll"}</h2>
              <p className="muted">{paid ? "The paid run stays frozen. The revision records only employee-level differences." : "The replacement revision copies existing cash advance, earning, and deduction values so you can edit them directly."}</p>
            </div>
          </div>

          <div className="grid cols-3">
            <div><strong>{delta.change_count}</strong><p className="muted">source change(s)</p></div>
            <div><strong>{paid ? "Already paid" : "Not yet paid"}</strong><p className="muted">Treatment is restricted automatically.</p></div>
            <div><strong>Original preserved</strong><p className="muted">The previous run remains available for audit.</p></div>
          </div>

          {delta.changed ? (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead><tr><th>Date</th><th>Type</th><th>Record</th><th>Changed by</th><th>Time</th></tr></thead>
                <tbody>{visibleChanges.map((change) => <tr key={change.id}><td>{change.work_date || "—"}</td><td>{change.change_type}</td><td>{change.entity_type}</td><td>{change.changed_by || "—"}</td><td>{change.changed_at}</td></tr>)}</tbody>
              </table>
            </div>
          ) : null}

          <div className="form-grid" style={{ marginTop: 12 }}>
            <label>Revision label<input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Optional revision label" /></label>
            <label>Revision reason<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder={paid ? "Required: why a paid adjustment is needed" : "Required: what values need correction"} /></label>
          </div>

          <fieldset style={{ marginTop: 12 }}>
            <legend>Revision treatment</legend>
            <label className="check-field"><input type="radio" checked={treatment === "replace_unpaid"} disabled={paid} onChange={() => setTreatment("replace_unpaid")} /><span><strong>Replace unpaid run</strong><br /><small className="muted">Copies prior manual values into a new Draft. Edit them as replacement amounts.</small></span></label>
            <label className="check-field" style={{ marginTop: 8 }}><input type="radio" checked={treatment === "adjust_paid"} disabled={!paid} onChange={() => setTreatment("adjust_paid")} /><span><strong>Create adjustment for paid run</strong><br /><small className="muted">Preserves prior values and records only the resulting employee difference.</small></span></label>
          </fieldset>

          {delta.changed ? <div className="form-grid" style={{ marginTop: 12 }}><label>Type UNDO to restore schedule/actuals<input value={confirmUndo} onChange={(event) => setConfirmUndo(event.target.value)} placeholder="UNDO" /></label></div> : null}

          <div className="action-row" style={{ marginTop: 12 }}>
            <button className="primary-button" type="button" disabled={busy !== null || !reason.trim()} onClick={saveRevision}>{busy === "revision" ? "Saving..." : paid ? "Create adjustment revision" : "Create editable replacement"}</button>
            {delta.changed ? <button className="button ghost" type="button" disabled={busy !== null || confirmUndo !== "UNDO"} onClick={undoChanges}>{busy === "undo" ? "Restoring..." : "Undo schedule/actual changes"}</button> : null}
            {delta.changed ? <Link className="button ghost" href={`/payroll/runs/${runId}/schedule-changes`}>View schedule changes</Link> : null}
            {message ? <span className="muted">{message}</span> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
