"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Item = {
  id: number;
  request_no: string;
  employee_name: string;
  employee_code?: string;
  department?: string;
  request_type: string;
  original_date: string;
  original_start_time: string;
  original_end_time: string;
  requested_date?: string | null;
  requested_start_time?: string | null;
  requested_end_time?: string | null;
  reason: string;
  swap_employee_name?: string | null;
  status: string;
  emergency: number;
  submitted_at: string;
  reviewed_by_name?: string | null;
  decision_note?: string | null;
  employee_notified?: number;
  coverage_confirmed?: number;
  attachment_path?: string | null;
};

async function post(body: Record<string, unknown>) {
  const response = await fetch("/api/schedule/shifts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || "Request failed.");
  return data;
}

export function ScheduleChangeReview() {
  const router = useRouter();
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    try {
      const data = await post({ operation: "review_requests" });
      setItems(data.items || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load requests.");
    }
  }

  useEffect(() => { void load(); }, []);

  async function decide(id: number, decision: "Approved" | "Rejected", form: HTMLFormElement) {
    setBusy(id);
    setError("");
    const data = new FormData(form);
    try {
      await post({
        operation: "decide_request",
        request_id: id,
        decision,
        decision_note: String(data.get("decision_note") || ""),
        employee_notified: data.get("employee_notified") === "on",
        coverage_confirmed: data.get("coverage_confirmed") === "on",
        apply_change: data.get("apply_change") === "on",
      });
      await load();
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Decision failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid">
      <div className="print-actions"><button className="button secondary" type="button" onClick={() => window.print()}>Print requests</button></div>
      {error ? <section className="card"><strong>Could not complete action</strong><p className="muted">{error}</p></section> : null}
      {items.map((item) => {
        const pending = ["Pending", "Emergency Review"].includes(item.status);
        const isSwap = item.request_type.trim().toLowerCase() === "shift swap";
        return (
          <article className="card shift-request-print" key={item.id}>
            <div className="panel-title">
              <div><span className="eyebrow">{item.request_no}</span><h2>{item.employee_name}</h2><p className="muted">{item.employee_code || "—"} · {item.department || "Unassigned"} · submitted {item.submitted_at}</p></div>
              <strong>{item.status}{item.emergency ? " · Emergency" : ""}</strong>
            </div>
            <div className="grid cols-3">
              <div><strong>Original shift</strong><p>{item.original_date}<br />{item.original_start_time}–{item.original_end_time}</p></div>
              <div><strong>Requested shift</strong><p>{item.requested_date || item.original_date}<br />{item.requested_start_time || item.original_start_time}–{item.requested_end_time || item.original_end_time}</p></div>
              <div><strong>Request type</strong><p>{item.request_type}{item.swap_employee_name ? <><br />Swap with {item.swap_employee_name}</> : null}</p></div>
            </div>
            <div><strong>Reason</strong><p>{item.reason}</p></div>
            {item.attachment_path ? <p className="muted">Supporting document is attached to this request.</p> : null}
            {isSwap ? <p className="muted"><strong>Swap control:</strong> Approving records management consent only. Update both employees’ shifts on the Schedule board so neither shift is changed only halfway.</p> : null}
            {item.decision_note ? <div><strong>Decision note</strong><p>{item.decision_note}</p></div> : null}
            {pending ? (
              <form className="grid cols-2" onSubmit={(event) => event.preventDefault()}>
                <label className="field" style={{ gridColumn: "1 / -1" }}>Decision note<textarea name="decision_note" rows={3} /></label>
                <label><input type="checkbox" name="coverage_confirmed" /> Coverage confirmed</label>
                <label><input type="checkbox" name="employee_notified" /> Employee notified</label>
                {isSwap ? <input type="hidden" name="apply_change" value="off" /> : <label><input type="checkbox" name="apply_change" defaultChecked /> Apply approved change to official schedule</label>}
                <div className="badge-row">
                  <button className="button" type="button" disabled={busy === item.id} onClick={(event) => decide(item.id, "Approved", event.currentTarget.form!)}>Approve</button>
                  <button className="button secondary" type="button" disabled={busy === item.id} onClick={(event) => decide(item.id, "Rejected", event.currentTarget.form!)}>Reject</button>
                </div>
              </form>
            ) : <p className="muted">Reviewed by {item.reviewed_by_name || "management"}. Coverage: {item.coverage_confirmed ? "confirmed" : "not recorded"}. Employee notification: {item.employee_notified ? "recorded" : "not recorded"}.</p>}
          </article>
        );
      })}
      {!items.length && !error ? <section className="card"><p className="muted">No shift-change requests yet.</p></section> : null}
    </div>
  );
}
