"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { PayrollRunChangeDelta } from "@/lib/api";

export function PayrollRevisionBanner({ runId, delta }: { runId: number; delta: PayrollRunChangeDelta }) {
  const router = useRouter();
  const [label, setLabel] = useState("");
  const [confirmUndo, setConfirmUndo] = useState("");
  const [busy, setBusy] = useState<"revision" | "undo" | null>(null);
  const [message, setMessage] = useState("");

  if (!delta.changed) return null;

  async function saveRevision() {
    setBusy("revision");
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/save-revision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_label: label || null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || data.message || "Could not save revised payroll run.");
      return;
    }
    const newId = data.run?.id;
    setMessage(newId ? `Revised payroll run #${newId} saved.` : "Revised payroll run saved.");
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
          <h2>Schedule or actual attendance changed after this payroll run was saved</h2>
          <p className="muted">This saved payroll run is still frozen. The changes below affect the current schedule/actual records only until you save a revised payroll run.</p>
        </div>
      </div>
      <div className="grid cols-3">
        <div><strong>{delta.change_count}</strong><p className="muted">logged change(s)</p></div>
        <div><strong>Saved run unchanged</strong><p className="muted">Payroll items below are the old snapshot.</p></div>
        <div><strong>Choose action</strong><p className="muted">Save revision or undo the changed records.</p></div>
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
        <label>Type UNDO to restore schedule/actuals<input value={confirmUndo} onChange={(event) => setConfirmUndo(event.target.value)} placeholder="UNDO" /></label>
      </div>
      <div className="action-row" style={{ marginTop: 12 }}>
        <button className="primary-button" type="button" disabled={busy !== null} onClick={saveRevision}>{busy === "revision" ? "Saving..." : "Save revised payroll run"}</button>
        <button className="button ghost" type="button" disabled={busy !== null || confirmUndo !== "UNDO"} onClick={undoChanges}>{busy === "undo" ? "Restoring..." : "Undo schedule/actual changes"}</button>
        {message ? <span className="muted">{message}</span> : null}
      </div>
    </section>
  );
}
