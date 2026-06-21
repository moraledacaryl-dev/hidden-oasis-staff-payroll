"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { PayrollRunChangeDelta } from "@/lib/api";

export function PayrollRevisionBanner({ runId, delta, runStatus, paidAt }: { runId: number; delta: PayrollRunChangeDelta; runStatus?: string | null; paidAt?: string | null }) {
  const router = useRouter();
  const paid = Boolean(paidAt) || ["paid", "released"].includes(String(runStatus || "").toLowerCase());
  const [label, setLabel] = useState("");
  const [reason, setReason] = useState("");
  const [treatment, setTreatment] = useState<"replace_unpaid" | "adjust_paid">(paid ? "adjust_paid" : "replace_unpaid");
  const [confirmUndo, setConfirmUndo] = useState("");
  const [busy, setBusy] = useState<"revision" | "undo" | null>(null);
  const [message, setMessage] = useState("");

  if (!delta.changed) return null;

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
      body: JSON.stringify({
        run_label: label || null,
        revision_reason: reason.trim(),
        treatment,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || data.message || "Could not save revised payroll run.");
      return;
    }
    const newId = data.run?.id;
    const summary = data.adjustment_summary;
    if (treatment === "adjust_paid" && summary) {
      setMessage(`Revision saved. Additional pay: ₱${Number(summary.additional_pay || 0).toLocaleString("en-PH", { minimumFractionDigits: 2 })}; recoverable: ₱${Number(summary.recoverable || 0).toLocaleString("en-PH", { minimumFractionDigits: 2 })}.`);
    } else {
      setMessage(newId ? `Revised payroll run #${newId} saved.` : "Revised payroll run saved.");
    }
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
    <section className="card danger-card">
      <div className="panel-title">
        <div>
          <span className="eyebrow">Changes detected</span>
          <h2>Schedule or attendance changed after this payroll run was saved</h2>
          <p className="muted">The saved run remains frozen. Create a linked revision from the corrected records or undo the changes.</p>
        </div>
      </div>

      <div className="grid cols-3">
        <div><strong>{delta.change_count}</strong><p className="muted">logged change(s)</p></div>
        <div><strong>{paid ? "Already paid" : "Not yet paid"}</strong><p className="muted">The revision treatment is restricted accordingly.</p></div>
        <div><strong>Original preserved</strong><p className="muted">The previous payroll remains available for audit.</p></div>
      </div>

      <div className="table-wrap" style={{ marginTop: 12 }}>
        <table>
          <thead><tr><th>Date</th><th>Type</th><th>Record</th><th>Changed by</th><th>Time</th></tr></thead>
          <tbody>
            {visibleChanges.map((change) => (
              <tr key={change.id}>
                <td>{change.work_date || "—"}</td>
                <td>{change.change_type}</td>
                <td>{change.entity_type}</td>
                <td>{change.changed_by || "—"}</td>
                <td>{change.changed_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="form-grid" style={{ marginTop: 12 }}>
        <label>Revision label<input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Optional, e.g. June 1-15 Revision" /></label>
        <label>Revision reason<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Required: what changed and why" /></label>
      </div>

      <fieldset style={{ marginTop: 12 }}>
        <legend>Revision treatment</legend>
        <label className="check-field">
          <input type="radio" checked={treatment === "replace_unpaid"} disabled={paid} onChange={() => setTreatment("replace_unpaid")} />
          <span><strong>Replace unpaid run</strong><br /><small className="muted">Use when the original run has not been paid. The revised run becomes the operational replacement.</small></span>
        </label>
        <label className="check-field" style={{ marginTop: 8 }}>
          <input type="radio" checked={treatment === "adjust_paid"} disabled={!paid} onChange={() => setTreatment("adjust_paid")} />
          <span><strong>Create adjustment for paid run</strong><br /><small className="muted">Use after payment. Only the difference per employee is recorded as additional pay or recoverable amount.</small></span>
        </label>
      </fieldset>

      <div className="form-grid" style={{ marginTop: 12 }}>
        <label>Type UNDO to restore schedule/actuals<input value={confirmUndo} onChange={(event) => setConfirmUndo(event.target.value)} placeholder="UNDO" /></label>
      </div>

      <div className="action-row" style={{ marginTop: 12 }}>
        <button className="primary-button" type="button" disabled={busy !== null || !reason.trim()} onClick={saveRevision}>{busy === "revision" ? "Saving..." : paid ? "Create adjustment revision" : "Create replacement revision"}</button>
        <button className="button ghost" type="button" disabled={busy !== null || confirmUndo !== "UNDO"} onClick={undoChanges}>{busy === "undo" ? "Restoring..." : "Undo schedule/actual changes"}</button>
        <Link className="button ghost" href={`/payroll/runs/${runId}/schedule-changes`}>View schedule changes</Link>
        {message ? <span className="muted">{message}</span> : null}
      </div>
    </section>
  );
}
